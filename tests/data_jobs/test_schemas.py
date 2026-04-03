from app.services.data_jobs.schemas import JobSubmitRequest


def test_job_submit_request_defaults():
    req = JobSubmitRequest(job_type="stock_basic")
    assert req.job_type == "stock_basic"
    assert req.full_refresh is False
    assert req.params == {}
