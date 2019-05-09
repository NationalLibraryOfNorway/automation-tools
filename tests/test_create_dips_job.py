#!/usr/bin/env python
import os
import unittest
import vcr

from sqlalchemy import exc

from aips import create_dips_job
from tests.tests_helpers import TmpDir

try:
    import mock
except ImportError:
    from unittest import mock


SS_URL = "http://192.168.168.192:8000"
SS_USER_NAME = "test"
SS_API_KEY = "12883879c823f6e533738c12266bfe9f7316a672"
LOCATION_UUID = "e9a08ce2-4e8e-4e01-bdea-09d8d8deff8b"

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
TMP_DIR = os.path.join(THIS_DIR, ".tmp-create-dips-job")
OUTPUT_DIR = os.path.join(TMP_DIR, "output")
DATABASE_FILE = os.path.join(TMP_DIR, "aips.db")


class TestCreateDipsJob(unittest.TestCase):
    def test_filter_aips(self):
        """
        Test that AIPs without 'uuid' or 'current_location'
        or in a different location are filtered.
        """
        aips = [
            {
                "current_location": "/api/v2/location/5c1c87e0-7d11-4f39-8dda-182b3a45031f/",
                "uuid": "7636f290-0b02-4323-b4bc-bd1ed191aaea",
            },
            {
                "current_location": "/api/v2/location/e9a08ce2-4e8e-4e01-bdea-09d8d8deff8b/",
                "uuid": "0fef53b0-0573-4398-aa4f-ebf04fe711cf",
            },
            {"uuid": "7636f290-0b02-4323-b4bc-bd1ed191aaea"},
            {
                "current_location": "/api/v2/location/e9a08ce2-4e8e-4e01-bdea-09d8d8deff8b/"
            },
        ]
        filtered_aips = create_dips_job.filter_aips(aips, LOCATION_UUID)
        assert filtered_aips == ["0fef53b0-0573-4398-aa4f-ebf04fe711cf"]

    def test_main_fail_db(self):
        """Test a fail when a database can't be created."""
        args = {
            "ss_url": SS_URL,
            "ss_user": SS_USER_NAME,
            "ss_api_key": SS_API_KEY,
            "location_uuid": LOCATION_UUID,
            "tmp_dir": TMP_DIR,
            "output_dir": OUTPUT_DIR,
            "database_file": "/this/should/be/a/wrong/path/to.db",
            "upload_type": None,
        }
        ret = create_dips_job.main(args)
        assert ret == 1

    @vcr.use_cassette("fixtures/vcr_cassettes/create_dips_job_main_fail_request.yaml")
    def test_main_fail_request(self):
        """Test a fail when an SS connection can't be established."""
        with TmpDir(TMP_DIR):
            args = {
                "ss_url": SS_URL,
                "ss_user": SS_USER_NAME,
                "ss_api_key": "bad_api_key",
                "location_uuid": LOCATION_UUID,
                "tmp_dir": TMP_DIR,
                "output_dir": OUTPUT_DIR,
                "database_file": DATABASE_FILE,
                "upload_type": None,
            }
            ret = create_dips_job.main(args)
            assert ret == 2

    @vcr.use_cassette("fixtures/vcr_cassettes/create_dips_job_main_success.yaml")
    def test_main_success(self):
        """Test a success where one DIP is created."""
        with TmpDir(TMP_DIR), TmpDir(OUTPUT_DIR):
            args = {
                "ss_url": SS_URL,
                "ss_user": SS_USER_NAME,
                "ss_api_key": SS_API_KEY,
                "location_uuid": LOCATION_UUID,
                "tmp_dir": TMP_DIR,
                "output_dir": OUTPUT_DIR,
                "database_file": DATABASE_FILE,
                "upload_type": None,
            }
            ret = create_dips_job.main(args)
            assert ret is None
            dip_path = os.path.join(
                OUTPUT_DIR, "test_B-3ea465ac-ea0a-4a9c-a057-507e794de332"
            )
            assert os.path.isdir(dip_path)

    @vcr.use_cassette("fixtures/vcr_cassettes/create_dips_job_main_success.yaml")
    def test_main_success_no_dip_creation(self):
        """Test a success where one AIP was already processed."""
        effect = exc.IntegrityError({}, [], "")
        session_add_patch = mock.patch("sqlalchemy.orm.Session.add", side_effect=effect)
        with TmpDir(TMP_DIR), TmpDir(OUTPUT_DIR), session_add_patch:
            args = {
                "ss_url": SS_URL,
                "ss_user": SS_USER_NAME,
                "ss_api_key": SS_API_KEY,
                "location_uuid": LOCATION_UUID,
                "tmp_dir": TMP_DIR,
                "output_dir": OUTPUT_DIR,
                "database_file": DATABASE_FILE,
                "upload_type": None,
            }
            ret = create_dips_job.main(args)
            assert ret is None
            dip_path = os.path.join(
                OUTPUT_DIR, "test_B_3ea465ac-ea0a-4a9c-a057-507e794de332_DIP"
            )
            assert not os.path.isdir(dip_path)
