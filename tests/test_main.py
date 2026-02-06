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
        # We expect 3 conversions total
        mock_downloader_instance.next_chunk.side_effect = [(None, True)] * 3
        
        # Mock io.BytesIO
        mock_buffer = MagicMock()
        mock_buffer.getvalue.return_value = b"<h1>Title</h1><p>Content</p>"
        mock_io_cls.return_value = mock_buffer
        
        # Run main
        main.main(dry_run=False)
        
        # Verify export called for 3 files
        assert mock_files.export_media.call_count == 3
        
        # Verify files created
        output_dir_1 = tmp_path / 'downloads' / 'Test Folder'
        assert (output_dir_1 / 'Doc 1.md').exists()
        assert (output_dir_1 / 'Doc 2.md').exists()
        
        output_dir_2 = tmp_path / 'downloads' / 'Folder'
        assert (output_dir_2 / 'Doc 3.md').exists()
        
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
        mock_downloader_instance.next_chunk.side_effect = [(None, True)] * 2
        
        # Mock io
        mock_buffer = MagicMock()
        mock_buffer.getvalue.return_value = b"<h1>Title</h1>"
        mock_io_cls.return_value = mock_buffer
        
        # Run
        main.main(dry_run=False)
        
        # Verify
        output_dir = tmp_path / 'custom_output'
        assert output_dir.exists()
        assert (output_dir / 'Doc 1.md').exists()
        
        # Verify recursive output
        sub_dir = output_dir / 'Sub'
        assert sub_dir.exists()
        assert (sub_dir / 'Doc 2.md').exists()

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
        
        # Verify no files created
        output_dir = tmp_path / 'downloads' / 'Test Folder'
        assert not output_dir.exists()
        
        # Verify state not updated (should still match initial state)
        with open(mock_state, 'r') as f:
            state = json.load(f)
            assert state == initial_state
            assert 'file1' not in state
