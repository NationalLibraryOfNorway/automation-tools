#!/usr/bin/env python
import os
import shutil
import unittest
import vcr

try:
    import mock
except ImportError:
    from unittest import mock

import requests

from dips import storage_service_upload

SS_URL = "http://localhost:62081"
SS_USER_NAME = "test"
SS_API_KEY = "test"
PIPELINE_UUID = "88050c7f-36a3-4900-9294-5a0411d69303"
CP_LOCATION_UUID = "e6409b38-20e9-4739-bb4a-892f2fb300d3"
DS_LOCATION_UUID = "6bbd3dee-b52f-476f-8136-bb3f0d025096"
SHARED_DIRECTORY = "/home/radda/.am/am-pipeline-data/"
DIP_PATH = "/tmp/fake_DIP"
AIP_UUID = "b9cd796c-2231-42e6-9cd1-0236d22958fa"


class TestSsUpload(unittest.TestCase):
    @mock.patch("dips.storage_service_upload.os.path.exists", return_value=True)
    def test_dip_folder_exists(self, moch_path_exists):
        ret = storage_service_upload.main(
            ss_url=SS_URL,
            ss_user=SS_USER_NAME,
            ss_api_key=SS_API_KEY,
            pipeline_uuid=PIPELINE_UUID,
            cp_location_uuid=CP_LOCATION_UUID,
            ds_location_uuid=DS_LOCATION_UUID,
            shared_directory=SHARED_DIRECTORY,
            dip_path=DIP_PATH,
            aip_uuid=AIP_UUID,
            delete_local_copy=True,
        )
        assert ret == 1

    @mock.patch(
        "dips.storage_service_upload.shutil.copytree", side_effect=shutil.Error("")
    )
    def test_dip_folder_copy_fail(self, moch_copytree):
        ret = storage_service_upload.main(
            ss_url=SS_URL,
            ss_user=SS_USER_NAME,
            ss_api_key=SS_API_KEY,
            pipeline_uuid=PIPELINE_UUID,
            cp_location_uuid=CP_LOCATION_UUID,
            ds_location_uuid=DS_LOCATION_UUID,
            shared_directory=SHARED_DIRECTORY,
            dip_path=DIP_PATH,
            aip_uuid=AIP_UUID,
            delete_local_copy=True,
        )
        assert ret == 2

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_storage_service_upload_request_fail.yaml"
    )
    @mock.patch("dips.storage_service_upload.shutil.copytree")
    def test_request_fail(self, moch_copytree):
        ret = storage_service_upload.main(
            ss_url=SS_URL,
            ss_user=SS_USER_NAME,
            ss_api_key="fake_api_key",
            pipeline_uuid=PIPELINE_UUID,
            cp_location_uuid=CP_LOCATION_UUID,
            ds_location_uuid=DS_LOCATION_UUID,
            shared_directory=SHARED_DIRECTORY,
            dip_path=DIP_PATH,
            aip_uuid=AIP_UUID,
            delete_local_copy=True,
        )
        assert ret == 3

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_storage_service_upload_async_fail.yaml"
    )
    @mock.patch(
        "dips.storage_service_upload.check_async",
        side_effect=requests.exceptions.RequestException(""),
    )
    @mock.patch("dips.storage_service_upload.shutil.copytree")
    def test_async_fail(self, moch_copytree, mock_check_async):
        ret = storage_service_upload.main(
            ss_url=SS_URL,
            ss_user=SS_USER_NAME,
            ss_api_key=SS_API_KEY,
            pipeline_uuid=PIPELINE_UUID,
            cp_location_uuid=CP_LOCATION_UUID,
            ds_location_uuid=DS_LOCATION_UUID,
            shared_directory=SHARED_DIRECTORY,
            dip_path=DIP_PATH,
            aip_uuid=AIP_UUID,
            delete_local_copy=True,
        )
        assert ret == 4

    @vcr.use_cassette("fixtures/vcr_cassettes/test_storage_service_upload_success.yaml")
    @mock.patch("dips.atom_upload.shutil.rmtree")
    @mock.patch(
        "dips.storage_service_upload.check_async", return_value={"uuid": "fake_uuid"}
    )
    @mock.patch("dips.storage_service_upload.shutil.copytree")
    def test_success(self, moch_copytree, mock_check_async, mock_rmtree):
        ret = storage_service_upload.main(
            ss_url=SS_URL,
            ss_user=SS_USER_NAME,
            ss_api_key=SS_API_KEY,
            pipeline_uuid=PIPELINE_UUID,
            cp_location_uuid=CP_LOCATION_UUID,
            ds_location_uuid=DS_LOCATION_UUID,
            shared_directory=SHARED_DIRECTORY,
            dip_path=DIP_PATH,
            aip_uuid=AIP_UUID,
            delete_local_copy=True,
        )
        assert ret == 0
        upload_dip_path = os.path.join(
            SHARED_DIRECTORY,
            "watchedDirectories",
            "uploadDIP",
            os.path.basename(DIP_PATH),
        )
        mock_rmtree.assert_has_calls([mock.call(upload_dip_path), mock.call(DIP_PATH)])
