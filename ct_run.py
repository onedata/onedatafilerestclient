#!/usr/bin/env python3

"""Runs integration tests."""

import argparse
import os
import platform
import subprocess
import sys
import time

script_dir = os.path.dirname(os.path.realpath(__file__))
docker_dir = os.path.join("bamboos", "docker")
sys.path.insert(0, docker_dir)
from environment import docker, dockers_config

parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description="Run Common Tests.",
)

parser.add_argument(
    "--onenv-config",
    action="store",
    help="run tests in one-env environment",
    dest="onenv_config",
)

parser.add_argument(
    "--no-clean",
    action="store_true",
    default=False,
    help="do not clean the one-env deployment after test",
    dest="no_clean",
)

parser.add_argument(
    "--image",
    "-i",
    action="store",
    default="onedata/pybuilder:v2",
    help="docker image to use as a test master",
    dest="image",
)

parser.add_argument(
    "--suite", action="append", default=[], help="name of the test suite", dest="suites"
)

parser.add_argument(
    "--no-shed-privileges",
    action="store_true",
    default=False,
    help="Run tests as root in container",
    dest="no_shed_privileges",
)


[args, _pass_args] = parser.parse_known_args()
dockers_config.ensure_image(args, "image", "builder")


script_dir = os.path.dirname(os.path.realpath(__file__))

base_test_dir = os.path.realpath("tests")

test_dirs = map(lambda suite: os.path.join(base_test_dir, suite), args.suites)
if not test_dirs:
    test_dirs = [base_test_dir]

envs = {
    "BASE_TEST_DIR": base_test_dir,
    "PYTHONWARNINGS": "ignore:Unverified HTTPS request",
}

# Setup oneenv environment
if args.onenv_config is not None:
    if not os.path.exists(args.onenv_config):
        print(f"Error: No such one-env file {args.onenv_config}")
        sys.exit(1)

    branch = os.popen("git rev-parse --abbrev-ref HEAD").read().strip()
    if branch.startswith("release/"):
        release_tag = branch.split("/", maxsplit=1)[-1]

        with open(args.onenv_config, "r+") as f:
            content = f.read()
            for repo in ("onezone-dev", "oneprovider-dev"):
                develop_image = f"docker.onedata.org/{repo}:develop"
                release_image = f"docker.onedata.org/{repo}:{release_tag}"
                content = content.replace(develop_image, release_image)
            f.seek(0)
            f.truncate()
            f.write(content)

    try:
        up_output = subprocess.check_output(
            ["./one-env/onenv", "up", args.onenv_config]
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to start onenv up due to: {e.output}")
        sys.exit(1)

    environment_ready = False
    retries = 3
    while (not environment_ready) and retries > 0:
        try:
            subprocess.check_call(["./one-env/onenv", "wait"])
            environment_ready = True
        except subprocess.CalledProcessError as e:
            retries -= 1
            time.sleep(5)
            print("Waiting for one-env environment setup...")

    if retries == 0:
        print(f"Failed to start K8S environment from {args.onenv_config}")
        sys.exit(1)

    print("One-env environment ready")

    # Get Onezone IP
    get_onezoneip_cli = "kubectl get pod dev-onezone-0 --template {{.status.podIP}}"
    onezone_ip = subprocess.check_output(get_onezoneip_cli.split(" ")).strip()
    envs["DEV_ONEZONE_0"] = onezone_ip.decode("utf-8")

    # Get Oneprovider IP
    get_oneproviderip_cli = (
        "kubectl get pod dev-oneprovider-krakow-0 --template {{.status.podIP}}"
    )
    oneprovider_ip = subprocess.check_output(get_oneproviderip_cli.split(" ")).strip()
    envs["DEV_ONEPROVIDER_KRAKOW_0"] = oneprovider_ip.decode("utf-8")

    get_oneprovider2ip_cli = (
        "kubectl get pod dev-oneprovider-paris-0 --template {{.status.podIP}}"
    )
    oneprovider_2_ip = subprocess.check_output(
        get_oneprovider2ip_cli.split(" ")
    ).strip()
    envs["DEV_ONEPROVIDER_PARIS_0"] = oneprovider_2_ip.decode("utf-8")

    print(f"Environment passed to pytest container: {str(envs)}")


command = """
import os, subprocess, sys, stat, shutil

if {shed_privileges}:
    os.environ['HOME'] = '/tmp'
    docker_gid = os.stat('/var/run/docker.sock').st_gid
    os.chmod('/etc/resolv.conf', 0o666)
    os.setgroups([docker_gid])
    os.setregid({gid}, {gid})
    os.setreuid({uid}, {uid})

tests = 'tests'
if '{suites}':
    tests = '{suites}'

command = ['python3'] + ['-m'] + ['tox'] +  ['-c'] + ['tox.ini'] + ['-e'] + [tests]
ret = subprocess.call(command)
sys.exit(ret)
"""
command = command.format(
    uid=os.geteuid(),
    gid=os.getegid(),
    shed_privileges=(platform.system() == "Linux") and not args.no_shed_privileges,
    suites=",".join(args.suites),
)

ret = docker.run(
    tty=True,
    rm=True,
    interactive=True,
    workdir=script_dir,
    volumes=[(script_dir, script_dir, "rw")],
    reflect=[("/var/run/docker.sock", "rw")],
    image=args.image,
    envs=envs,
    run_params=["--privileged"] if args.no_shed_privileges else [],
    command=["python3", "-c", command],
)

if not args.no_clean:
    try:
        up_output = subprocess.check_output(["./one-env/onenv", "clean"])
    except subprocess.CalledProcessError as e:
        print(f"Failed to clean onenv due to: {e.output}")
        sys.exit(1)

sys.exit(ret)
