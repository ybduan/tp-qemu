import os
import re
import time

from avocado.utils import process
from virttest import data_dir, env_process, error_context, utils_misc


@error_context.context_aware
def run(test, params, env):
    """
    TestStep:
    1) Exec the stap script in host
    2) Boot the guest, and do some operation(if needed).
    3) Check the output of the stap
    params:
    :param test: kvm test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """

    def create_patterns_reg(trace_key):
        """
        Create a regular exp using the tracing key, the purpose is checking
        the systemtap output is accord with expected.
        """
        pattern_reg = r""
        for tracing_key in trace_key.split():
            pattern_reg += r"%s=\d+," % tracing_key
        return pattern_reg.rstrip(",")

    error_context.base_context("Qemu_Tracing Test")
    error_context.context("Test start ...")

    probe_var_key = params.get("probe_var_key")
    checking_pattern_re = create_patterns_reg(probe_var_key)
    capdata_timeout = int(params.get("capdata_timeout", "360"))
    timeout = int(params.get("login_timeout", "360"))
    time_inter = int(params.get("time_inter", "1"))

    if params.get("extra_params"):
        params["extra_params"] = params.get("extra_params")

    if params.get("boot_with_cdrom") == "yes":
        iso_path = "%s/test.iso" % data_dir.get_tmp_dir()
        create_cmd = "dd if=/dev/zero of=%s bs=1M count=10" % iso_path
        if process.system(create_cmd, ignore_status=True) != 0:
            test.cancel("Create test iso failed")
        params["cdrom_cd1"] = iso_path

    if params.get("start_vm", "yes") == "no":
        params["start_vm"] = "yes"
        env_process.preprocess_vm(test, params, env, params.get("main_vm"))

    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    _params = params.object_params(vm.monitor.protocol)
    if _params.get("cmds_exec"):
        for cmd in _params.get("cmds_exec").split(","):
            if re.findall(":", cmd):
                cmd_type = cmd.split(":")[0]
                exec_cmds = cmd.split(":")[1]
            else:
                cmd_type = "bash"
                exec_cmds = cmd
            for cmd_exec in exec_cmds.split(";"):
                msg = "Execute %s cmd '%s'" % (cmd_type, cmd_exec)
                error_context.context(msg, test.log.info)
                if cmd_type == "monitor":
                    vm.monitor.send_args_cmd(cmd_exec)
                elif cmd_type == "bash":
                    guest_session = vm.wait_for_login(timeout=timeout)
                    guest_session.cmd(cmd_exec)

    error_context.context("Get the output of stap script", test.log.info)
    stap_log_file = utils_misc.get_path(test.profdir, "systemtap.log")

    start_time = time.time()
    while (time.time() - start_time) < capdata_timeout:
        if os.path.isfile(stap_log_file):
            fd = open(stap_log_file, "r")
            data = fd.read()
            if (not data) or (not re.findall(checking_pattern_re, data)):
                time.sleep(time_inter)
                fd.close()
                continue
            elif data and re.findall(checking_pattern_re, data):
                test.log.info("Capture the data successfully")
                test.log.info(
                    "The capture data is like: %s",
                    re.findall(checking_pattern_re, data)[-1],
                )
                fd.close()
                break
        else:
            time.sleep(time_inter)
    else:
        test.error("Timeout for capature the stap log data")
