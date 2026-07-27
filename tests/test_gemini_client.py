import pytest
from unittest.mock import patch, MagicMock
from src.gemini_client import call_gemini_with_failover
from src.models import ReviewReport, ReviewIssue
import src.gemini_client as gc

@patch('src.gemini_client.time.sleep')
@patch('src.gemini_client.API_TIMEOUT_SECONDS', 1)
@patch('src.gemini_client.MAX_RETRIES', 3)
def test_successful_first_model(mock_sleep):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_report = ReviewReport(analysis_scratchpad="test", issues=[])
    mock_response.parsed = mock_report
    mock_client.models.generate_content.return_value = mock_response

    result = call_gemini_with_failover(mock_client, "prompt")
    assert result == mock_report
    assert mock_client.models.generate_content.call_count == 1

@patch('src.gemini_client.time.sleep')
@patch('src.gemini_client.API_TIMEOUT_SECONDS', 1)
@patch('src.gemini_client.MAX_RETRIES', 2)
def test_failover_to_second_model(mock_sleep):
    mock_client = MagicMock()
    
    mock_success_response = MagicMock()
    mock_report = ReviewReport(analysis_scratchpad="test2", issues=[])
    mock_success_response.parsed = mock_report
    
    # First model fails, second succeeds
    mock_client.models.generate_content.side_effect = [Exception("error"), mock_success_response]
    
    with patch('src.gemini_client.FAILOVER_MODELS', ['model1', 'model2']):
        # If MAX_RETRIES=2, it will try model1 twice, so side_effect needs 3 elements: error, error, success
        mock_client.models.generate_content.side_effect = [Exception("err1"), Exception("err2"), mock_success_response]
        result = call_gemini_with_failover(mock_client, "prompt")
        
        assert result == mock_report
        assert mock_client.models.generate_content.call_count == 3

@patch('src.gemini_client.time.sleep')
@patch('src.gemini_client.API_TIMEOUT_SECONDS', 1)
@patch('src.gemini_client.MAX_RETRIES', 1)
@patch('src.gemini_client.FAILOVER_MODELS', ['model-a'])
def test_all_models_exhausted_raises_runtime_error(mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("error")

    with pytest.raises(RuntimeError) as exc_info:
        call_gemini_with_failover(mock_client, "prompt")
    
    assert "Failed to generate review after trying all fallback models" in str(exc_info.value)

@patch('src.gemini_client.time.sleep')
@patch('src.gemini_client.API_TIMEOUT_SECONDS', 1)
@patch('src.gemini_client.MAX_RETRIES', 2)
def test_retry_on_empty_parsed_response(mock_sleep):
    mock_client = MagicMock()
    
    mock_empty_response = MagicMock()
    mock_empty_response.parsed = None
    
    mock_success_response = MagicMock()
    mock_report = ReviewReport(analysis_scratchpad="test3", issues=[])
    mock_success_response.parsed = mock_report
    
    mock_client.models.generate_content.side_effect = [mock_empty_response, mock_success_response]
    
    result = call_gemini_with_failover(mock_client, "prompt")
    
    assert result == mock_report
    assert mock_client.models.generate_content.call_count == 2
