#!/usr/bin/env python3
"""Entry point: starts the Jenkins MCP server on port 8080.

Usage:
    python jenkins.py

This script handles the module name collision between our local
'jenkins.py' and the installed 'jenkins' library (python-jenkins).
"""

import sys
import os

# 1) Temporarily remove current dir from sys.path so that the
#    installed 'jenkins' package (python-jenkins) can be imported.
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.realpath(p) != os.path.realpath(script_dir)]

# 2) Import the real jenkins library from site-packages
import jenkins as _jk  # noqa: E402

# 3) Restore our project dir to sys.path so our modules can be found
sys.path.insert(0, script_dir)

# 4) Import the MCP server module and inject the jenkins library into it
import jenkins_mcp_server  # noqa: E402
jenkins_mcp_server._init_jenkins_lib(_jk)

# 5) Run
jenkins_mcp_server.main()
