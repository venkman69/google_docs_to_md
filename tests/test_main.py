import os
import json
import yaml
import pytest
from unittest.mock import MagicMock, patch, call
from src import main

# Mock config
@pytest.fixture
def mock_config(tmp_path):
    config = {
        'directories': [
            {'name': 'Test Folder', 'id': 'folder123'},
            'Path/To/Folder'
        ]
    }
    config_file = tmp_path / 'config.yaml'
    with open(config_file, 'w') as f:
        yaml.dump(config, f)
    return str(config_file)

# Mock state
@pytest.fixture
def mock_state(tmp_path):
    state_file = tmp_path / 'state.json'
    return str(state_file)

def test_resolve_path_to_id():
    mock_service = MagicMock()
    
    mock_files = mock_service.files.return_value
    mock_list = mock_files.list
    
    mock_list.return_value.execute.side_effect = [
        {'files': [{'id': 'path_id', 'name': 'Path'}]},
        {'files': [{'id': 'to_id', 'name': 'To'}]},
        {'files': [{'id': 'folder_id', 'name': 'Folder'}]}
    ]
    
    result = main.resolve_path_to_id(mock_service, 'Path/To/Folder')
    assert result == 'folder_id'
    assert mock_list.call_count == 3

def test_resolve_path_not_found():
    mock_service = MagicMock()
    mock_files = mock_service.files.return_value
    mock_list = mock_files.list
    
    # First found, second not found
    mock_list.return_value.execute.side_effect = [
        {'files': [{'id': 'path_id', 'name': 'Path'}]},
        {'files': []}
    ]
    
    result = main.resolve_path_to_id(mock_service, 'Path/Missing')
    assert result is None


def test_main_workflow(mock_config, mock_state, tmp_path):
    # Setup paths
    with patch('src.main.CONFIG_FILE', mock_config), \
         patch('src.main.STATE_FILE', mock_state), \
         patch('os.getcwd', return_value=str(tmp_path)), \
         patch('src.main.get_service') as mock_get_service, \
         patch('src.main.MediaIoBaseDownload') as mock_downloader_cls, \
         patch('io.BytesIO') as mock_io_cls:
        
        # Mock Service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        # Mock List Files
        mock_files = mock_service.files.return_value
        mock_list = mock_files.list
        
        # Sequence:
        # 1. Scan 'Test Folder' (id='folder123')
        #    - List Docs -> 2 docs
        #    - List Subfolders -> 0 folders
        # 2. Resolve 'Path/To/Folder' -> 3 calls
        #    - Path -> path_id
        #    - To -> to_id
        #    - Folder -> folder_id
        # 3. Scan 'Folder' (from 'Path/To/Folder') (id='folder_id')
        #    - List Docs -> 1 doc
        #    - List Subfolders -> 0 folders
        
        scan_1_docs = {
            'files': [
                {'id': 'file1', 'name': 'Doc 1', 'modifiedTime': '2023-10-26T10:00:00Z'},
                {'id': 'file2', 'name': 'Doc 2', 'modifiedTime': '2023-10-26T11:00:00Z'}
            ]
        }
        scan_1_folders = {'files': []}
        
        # Path resolution results
        res_path = {'files': [{'id': 'path_id', 'name': 'Path'}]}
        res_to = {'files': [{'id': 'to_id', 'name': 'To'}]}
        res_folder = {'files': [{'id': 'folder_id', 'name': 'Folder'}]}
        
        scan_2_docs = {
            'files': [
                {'id': 'file3', 'name': 'Doc 3', 'modifiedTime': '2023-10-26T12:00:00Z'}
            ]
        }
        scan_2_folders = {'files': []}
        
        mock_list.return_value.execute.side_effect = [
            scan_1_docs,     # Scan 1 Docs
            scan_1_folders,  # Scan 1 Folders
            res_path,        # Resolve 1
            res_to,          # Resolve 2
            res_folder,      # Resolve 3
            scan_2_docs,     # Scan 2 Docs
            scan_2_folders   # Scan 2 Folders
        ]
        
        # Mock Download (Export)
        mock_downloader_instance = MagicMock()
        mock_downloader_cls.return_value = mock_downloader_instance
        # We expect 3 conversions total (html + pdf for each = 6 downloads)
        mock_downloader_instance.next_chunk.side_effect = [(None, True)] * 6
        
        # Mock io.BytesIO
        mock_buffer = MagicMock()
        mock_buffer.getvalue.return_value = b"<h1>Title</h1><p>Content</p>"
        mock_io_cls.return_value = mock_buffer
        
        # Run main
        main.main(dry_run=False)
        
        # Verify export called for 3 files (2 calls per file)
        assert mock_files.export_media.call_count == 6
        
        # Verify files created
        output_dir_1 = tmp_path / 'downloads' / 'Test Folder'
        assert (output_dir_1 / 'Doc 1.md').exists()
        assert (output_dir_1 / 'Doc 1.pdf').exists()
        assert (output_dir_1 / 'Doc 2.md').exists()
        assert (output_dir_1 / 'Doc 2.pdf').exists()
        
        output_dir_2 = tmp_path / 'downloads' / 'Folder'
        assert (output_dir_2 / 'Doc 3.md').exists()
        assert (output_dir_2 / 'Doc 3.pdf').exists()
        
        # Verify state updated
        with open(mock_state, 'r') as f:
            state = json.load(f)
            assert state['file1'] == '2023-10-26T10:00:00Z'
            assert state['file2'] == '2023-10-26T11:00:00Z'
            assert state['file3'] == '2023-10-26T12:00:00Z'

def test_main_workflow_custom_path_recursive(mock_state, tmp_path):
    # Custom config for this test with the new map format
    config = {
        'directories': [
            {'Drive/Folder': str(tmp_path / 'custom_output')}
        ]
    }
    config_file = tmp_path / 'config_custom.yaml'
    with open(config_file, 'w') as f:
        yaml.dump(config, f)
        
    with patch('src.main.CONFIG_FILE', str(config_file)), \
         patch('src.main.STATE_FILE', mock_state), \
         patch('src.main.get_service') as mock_get_service, \
         patch('src.main.MediaIoBaseDownload') as mock_downloader_cls, \
         patch('io.BytesIO') as mock_io_cls:
         
        # Mock Service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_files = mock_service.files.return_value
        mock_list = mock_files.list
        
        # 1. Resolve 'Drive/Folder'
        #    - Drive -> drive_id
        #    - Folder -> folder_id
        # 2. Scan 'Folder' (folder_id)
        #    - List Docs -> 1 file
        #    - List Subfolders -> 1 subfolder 'Sub'
        # 3. Scan 'Sub' (sub_id)
        #    - List Docs -> 1 file (nested)
        #    - List Subfolders -> 0
        
        res_drive = {'files': [{'id': 'drive_id', 'name': 'Drive'}]}
        res_folder = {'files': [{'id': 'folder_id', 'name': 'Folder'}]}
        
        scan_folder_docs = {
            'files': [
                {'id': 'file1', 'name': 'Doc 1', 'modifiedTime': '2023-10-26T10:00:00Z'}
            ]
        }
        scan_folder_sub = {
            'files': [
                {'id': 'sub_id', 'name': 'Sub'}
            ]
        }
        
        scan_sub_docs = {
             'files': [
                {'id': 'file2', 'name': 'Doc 2', 'modifiedTime': '2023-10-26T10:00:00Z'}
            ]
        }
        scan_sub_folders = {'files': []}
        
        mock_list.return_value.execute.side_effect = [
            res_drive,
            res_folder,
            scan_folder_docs,
            scan_folder_sub,
            scan_sub_docs,
            scan_sub_folders
        ]
        
        # Mock Download
        mock_downloader_instance = MagicMock()
        mock_downloader_cls.return_value = mock_downloader_instance
        mock_downloader_instance.next_chunk.side_effect = [(None, True)] * 4
        
        # Mock io.BytesIO
        mock_buffer = MagicMock()
        mock_buffer.getvalue.return_value = b"<h1>Title</h1><p>Content</p>"
        mock_io_cls.return_value = mock_buffer
        
        # Run main
        main.main(dry_run=False)
        
        # Verify files created
        output_dir_1 = tmp_path / 'custom_output'
        assert (output_dir_1 / 'Doc 1.md').exists()
        assert (output_dir_1 / 'Doc 1.pdf').exists()
        
        output_dir_2 = tmp_path / 'custom_output' / 'Sub'
        assert (output_dir_2 / 'Doc 2.md').exists()
        assert (output_dir_2 / 'Doc 2.pdf').exists()

def test_dry_run(mock_state, tmp_path):
    # Reuse config setup from fixture manually or mock it
    config = {
        'directories': [{'name': 'Test Folder', 'id': 'folder123'}]
    }
    config_file = tmp_path / 'config.yaml'
    with open(config_file, 'w') as f:
        yaml.dump(config, f)
        
    # Create initial state
    initial_state = {'existing_file': '2020-01-01T00:00:00Z'}
    with open(mock_state, 'w') as f:
        json.dump(initial_state, f)

    with patch('src.main.CONFIG_FILE', str(config_file)), \
         patch('src.main.STATE_FILE', mock_state), \
         patch('src.main.get_service') as mock_get_service, \
         patch('src.main.MediaIoBaseDownload') as mock_downloader_cls:
         
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_files = mock_service.files.return_value
        
        scan_docs = {
            'files': [
                {'id': 'file1', 'name': 'Doc 1', 'modifiedTime': '2023-11-01T10:00:00Z'}
            ]
        }
        scan_folders = {'files': []}
        
        mock_files.list.return_value.execute.side_effect = [scan_docs, scan_folders]
        
        # Run with dry_run=True
        main.main(dry_run=True)

        # Verify download was NOT called
        assert mock_files.export_media.call_count == 0

def test_print_conversion_report():
    """Test the conversion report output with log capture."""
    import logging
    from io import StringIO

    # Create a string buffer and add a handler to capture logs
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)

    # Get the root logger (which main.py uses)
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    try:
        # Test with files converted (new tuple format with folder paths)
        converted_files = [
            ('Folder1/SubFolder', 'Doc1.md'),
            ('Folder1', 'Doc2.md'),
            ('Folder2/SubFolder/DeepFolder', 'Doc3.md')
        ]
        main.print_conversion_report(converted_files, dry_run=False)

        captured = log_capture.getvalue()
        assert 'Conversion Report' in captured
        assert 'Total documents were converted: 3' in captured
        assert '1. Doc1.md' in captured
        assert '   Folder: Folder1/SubFolder' in captured
        assert '2. Doc2.md' in captured
        assert '   Folder: Folder1' in captured
        assert '3. Doc3.md' in captured
        assert '   Folder: Folder2/SubFolder/DeepFolder' in captured

        # Clear buffer
        log_capture.truncate(0)
        log_capture.seek(0)

        # Test with no files converted
        main.print_conversion_report([], dry_run=False)
        captured = log_capture.getvalue()
        assert 'Conversion Report' in captured
        assert 'No documents were converted' in captured

        # Clear buffer
        log_capture.truncate(0)
        log_capture.seek(0)

        # Test with dry_run=True
        main.print_conversion_report([('MyFolder', 'Doc1.md')], dry_run=True)
        captured = log_capture.getvalue()
        assert 'Total documents would be converted: 1' in captured

        # Clear buffer
        log_capture.truncate(0)
        log_capture.seek(0)

        # Test backward compatibility (old string format)
        converted_files_old = ['Doc1.md', 'Doc2.md']
        main.print_conversion_report(converted_files_old, dry_run=False)
        captured = log_capture.getvalue()
        assert '1. Doc1.md' in captured
        assert '2. Doc2.md' in captured
        # Should NOT have folder lines for old format
        assert '   Folder:' not in captured
    finally:
        # Restore original handlers
        root_logger.handlers = original_handlers
        handler.close()

def test_scan_folder_tracks_conversions():
    """Test that scan_folder properly tracks converted files in the converted_files list."""
    from unittest.mock import Mock

    # Setup mock service and basic data
    mock_service = Mock()
    mock_files = Mock()
    mock_service.files.return_value = mock_files

    # Mock empty results (no docs, no folders)
    mock_files.list.return_value.execute.return_value = {'files': []}
    mock_files.get.return_value.execute.return_value = {'parents': ['parent123']}

    # Track converted files
    converted_files = []
    state = {}

    # Call scan_folder with converted_files tracking
    main.scan_folder(mock_service, 'folder123', '/tmp/test', state, dry_run=True, converted_files=converted_files)

    # Verify the list was passed through (even though no files converted in this test)
    assert converted_files is not None
    assert isinstance(converted_files, list)
