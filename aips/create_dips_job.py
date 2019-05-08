#!/usr/bin/env python
"""
Create DIPs from an SS location

Get all AIPs from an existing SS instance, filtering them by location,
creating DIPs using the `create_dip` script and keeping track of them
in an SQLite database.

Optionally, uploads those DIPs to AtoM or the Storage Service using
the scripts from `dips` and deletes the local copy.
"""

import argparse
import logging
import logging.config  # Has to be imported separately
import os
import sys

from sqlalchemy import exc

import amclient

from aips import create_dip
from aips import models
from dips import atom_upload, storage_service_upload

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
LOGGER = logging.getLogger("create_dip")


def setup_logger(log_file, log_level="INFO"):
    """Configures the logger to output to console and log file"""
    if not log_file:
        log_file = os.path.join(THIS_DIR, "create_dip.log")

    CONFIG = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "default": {
                "format": "%(levelname)-8s  %(asctime)s  %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "default"},
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": log_file,
                "backupCount": 2,
                "maxBytes": 10 * 1024,
            },
        },
        "loggers": {
            "create_dip": {"level": log_level, "handlers": ["console", "file"]}
        },
    }

    logging.config.dictConfig(CONFIG)


def main(args):
    LOGGER.info("Processing AIPs in SS location: %s", args["location_uuid"])

    # Idempotently create database and Aip table and create session
    try:
        session = models.init(args["database_file"])
    except IOError:
        LOGGER.error("Could not create database in: %s", args["database_file"])
        return 1

    # Get UPLOADED and VERIFIED AIPs from the SS
    try:
        am_client = amclient.AMClient(
            ss_url=args["ss_url"],
            ss_user_name=args["ss_user"],
            ss_api_key=args["ss_api_key"],
        )
        # There is an issue in the SS API that avoids
        # filtering the results by location. See:
        # https://github.com/artefactual/archivematica-storage-service/issues/298
        aips = am_client.aips({"status__in": "UPLOADED,VERIFIED"})
    except Exception as e:
        LOGGER.error(e)
        return 2

    # Get only AIPs from the specified location
    aip_uuids = filter_aips(aips, args["location_uuid"])

    # Create DIPs for those AIPs
    for uuid in aip_uuids:
        try:
            # To avoid race conditions while checking for an existing AIP
            # and saving it, create the row directly and check for an
            # integrity error exception (the uuid is a unique column)
            db_aip = models.Aip(uuid=uuid)
            session.add(db_aip)
            session.commit()
        except exc.IntegrityError:
            session.rollback()
            LOGGER.debug("Skipping AIP (already processed/processing): %s", uuid)
            continue

        mets_type = "atom"
        if args["upload_type"] == "ss-upload":
            mets_type = "storage-service"

        dip_path = create_dip.main(
            ss_url=args["ss_url"],
            ss_user=args["ss_user"],
            ss_api_key=args["ss_api_key"],
            aip_uuid=uuid,
            tmp_dir=args["tmp_dir"],
            output_dir=args["output_dir"],
            mets_type=mets_type,
        )

        if args["upload_type"] == "ss-upload":
            storage_service_upload.main(
                ss_url=args["ss_url"],
                ss_user=args["ss_user"],
                ss_api_key=args["ss_api_key"],
                pipeline_uuid=args["pipeline_uuid"],
                cp_location_uuid=args["cp_location_uuid"],
                ds_location_uuid=args["ds_location_uuid"],
                shared_directory=args["shared_directory"],
                dip_path=dip_path,
                aip_uuid=uuid,
                delete_local_copy=args["delete_local_copy"],
            )
        elif args["upload_type"] == "atom-upload":
            atom_upload.main(
                atom_url=args["atom_url"],
                atom_email=args["atom_email"],
                atom_password=args["atom_password"],
                atom_slug=args["atom_slug"],
                rsync_target=args["rsync_target"],
                dip_path=dip_path,
                delete_local_copy=args["delete_local_copy"],
            )

    LOGGER.info("All AIPs have been processed")


def filter_aips(aips, location_uuid):
    """
    Filters a list of AIPs based on a location UUID.

    :param list aips: list of AIPs from the results of an SS response
    :param str location_uuid: UUID from the SS location
    :returns: list of UUIDs from the AIPs in that location
    """
    location = "/api/v2/location/{}/".format(location_uuid)
    filtered_aips = []

    for aip in aips:
        if "uuid" not in aip:
            LOGGER.warning("Skipping AIP (missing UUID in SS response)")
            continue
        if "current_location" not in aip:
            LOGGER.debug("Skipping AIP (missing location): %s", aip["uuid"])
            continue
        if aip["current_location"] != location:
            LOGGER.debug("Skipping AIP (different location): %s", aip["uuid"])
            continue
        filtered_aips.append(aip["uuid"])

    return filtered_aips


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ss-url",
        metavar="URL",
        help="Storage Service URL. Default: http://127.0.0.1:8000",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--ss-user",
        metavar="USERNAME",
        required=True,
        help="Username of the Storage Service user to authenticate as.",
    )
    parser.add_argument(
        "--ss-api-key",
        metavar="KEY",
        required=True,
        help="API key of the Storage Service user.",
    )
    parser.add_argument(
        "--location-uuid",
        metavar="UUID",
        required=True,
        help="UUID of an AIP Storage location in the Storage Service.",
    )
    parser.add_argument(
        "--database-file",
        metavar="PATH",
        required=True,
        help="Absolute path to an SQLite database file.",
    )
    parser.add_argument(
        "--tmp-dir",
        metavar="PATH",
        help="Absolute path to the directory used for temporary files. Default: /tmp.",
        default="/tmp",
    )
    parser.add_argument(
        "--output-dir",
        metavar="PATH",
        help="Absolute path to the directory used to place the final DIP. Default: /tmp.",
        default="/tmp",
    )

    # Logging
    parser.add_argument(
        "--log-file", metavar="FILE", help="Location of log file", default=None
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase the debugging output.",
    )
    parser.add_argument(
        "--quiet", "-q", action="count", default=0, help="Decrease the debugging output"
    )
    parser.add_argument(
        "--log-level",
        choices=["ERROR", "WARNING", "INFO", "DEBUG"],
        default=None,
        help="Set the debugging output level. This will override -q and -v",
    )

    # Delete argument can't be set in the two subparsers bellow with the same name
    parser.add_argument(
        "--delete-local-copy",
        action="store_true",
        help="Deletes the local DIPs after upload if any of the upload arguments is used.",
    )

    # Create optional upload type subparsers
    subparsers = parser.add_subparsers(
        dest="upload_type",
        title="Upload options",
        description="The following arguments allow to upload the DIP after creation:",
        help="Leave empty to keep the DIP in the output path.",
    )

    # Storage Service upload subparser with extra SS required arguments
    parser_ss = subparsers.add_parser(
        "ss-upload",
        help="Storage Service upload. Check 'create_dips_job ss-upload -h'.",
    )
    parser_ss.add_argument(
        "--pipeline-uuid",
        metavar="UUID",
        required=True,
        help="UUID of the Archivemativa pipeline in the Storage Service",
    )
    parser_ss.add_argument(
        "--cp-location-uuid",
        metavar="UUID",
        required=True,
        help="UUID of the pipeline's Currently Processing location in the Storage Service",
    )
    parser_ss.add_argument(
        "--ds-location-uuid",
        metavar="UUID",
        required=True,
        help="UUID of the pipeline's DIP storage location in the Storage Service",
    )
    parser_ss.add_argument(
        "--shared-directory",
        metavar="PATH",
        help="Absolute path to the pipeline's shared directory.",
        default="/var/archivematica/sharedDirectory/",
    )

    # AtoM upload subparser with AtoM required arguments
    parser_atom = subparsers.add_parser(
        "atom-upload", help="AtoM upload. Check 'create_dips_job atom-upload -h'."
    )
    parser_atom.add_argument(
        "--atom-url",
        metavar="URL",
        help="AtoM instance URL. Default: http://192.168.168.193",
        default="http://192.168.168.193",
    )
    parser_atom.add_argument(
        "--atom-email",
        metavar="EMAIL",
        required=True,
        help="Email of the AtoM user to authenticate as.",
    )
    parser_atom.add_argument(
        "--atom-password",
        metavar="PASSWORD",
        required=True,
        help="Password of the AtoM user.",
    )
    parser_atom.add_argument(
        "--atom-slug",
        metavar="SLUG",
        required=True,
        help="AtoM archival description slug to target the upload.",
    )
    parser_atom.add_argument(
        "--rsync-target",
        metavar="HOST:PATH",
        help="Destination value passed to Rsync. Default: 192.168.168.193:/tmp.",
        default="192.168.168.193:/tmp",
    )

    args = parser.parse_args()

    log_levels = {2: "ERROR", 1: "WARNING", 0: "INFO", -1: "DEBUG"}
    if args.log_level is None:
        level = args.quiet - args.verbose
        level = max(level, -1)  # No smaller than -1
        level = min(level, 2)  # No larger than 2
        log_level = log_levels[level]
    else:
        log_level = args.log_level

    setup_logger(args.log_file, log_level)

    # Transform arguments to dict to pass them to the main function
    sys.exit(main(vars(args)))
