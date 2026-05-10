#!/usr/bin/env python3
"""
Jenkins MCP Server — FastMCP + SSE (HTTP) Transport
====================================================

Usage:
    python jenkins.py

Environment variables:
    JENKINS_URL       — Jenkins server URL (default: http://localhost:8080)
    JENKINS_USER      — Jenkins username
    JENKINS_PASSWORD  — Jenkins API token or password
    JENKINS_CA_BUNDLE — Optional path to CA bundle for TLS

The server listens on 0.0.0.0:8080 with SSE transport.
"""

import os
import json
import logging

# NOTE: 'import jenkins' is handled by the entry point (jenkins.py) which
# patches sys.path to avoid the local file shadowing the installed package.
# Here we just import the reference that was already set up.

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("jenkins-mcp")

# This will be set by the entry point before importing this module
jk = None  # type: ignore


def _init_jenkins_lib(lib):
    """Called by the entry point to inject the installed jenkins library."""
    global jk
    jk = lib


# ---------------------------------------------------------------------------
# Jenkins client
# ---------------------------------------------------------------------------

class JenkinsClient:
    """Thin wrapper around python-jenkins with our error handling."""

    def __init__(self):
        self.url = os.environ.get("JENKINS_URL", "http://localhost:8080").rstrip("/")
        self.user = os.environ.get("JENKINS_USER", "")
        self.password = os.environ.get("JENKINS_PASSWORD", "")
        ca_bundle = os.environ.get("JENKINS_CA_BUNDLE")

        kwargs: dict = {}
        if ca_bundle:
            kwargs["ca_bundle"] = ca_bundle

        self._server = jk.Jenkins(
            self.url,
            username=self.user,
            password=self.password,
            **kwargs,
        )
        try:
            ver = self._server.get_version()
            log.info("Connected to Jenkins %s (v%s)", self.url, ver)
        except Exception as exc:
            log.warning("Could not connect to Jenkins at %s: %s", self.url, exc)

    def trigger_build(self, jobname: str, params: dict | None = None) -> dict:
        """Trigger a Jenkins build (with optional parameters).

        All parameter values are normalized to strings before sending to
        Jenkins, because:
        - Boolean values must be lowercase ``"true"`` / ``"false"``
        - ``None`` values become empty string ``""``
        - Integer / float values are stringified
        """
        normalized: dict[str, str] = {}
        if params:
            for k, v in params.items():
                if v is None:
                    normalized[k] = ""
                elif isinstance(v, bool):
                    normalized[k] = "true" if v else "false"
                elif isinstance(v, (int, float)):
                    normalized[k] = str(v)
                else:
                    normalized[k] = str(v)
        queue_id = self._server.build_job(jobname, parameters=normalized)
        return {"queue_id": queue_id, "job": jobname, "parameters": normalized}

    def stop_build(self, jobname: str, build_number: int) -> dict:
        """Stop / abort a running build."""
        result = self._server.stop_build(jobname, build_number)
        return {"job": jobname, "build_number": build_number, "stopped": result}

    def get_job(self, jobname: str) -> dict:
        """Return full metadata for a single job."""
        info = self._server.get_job_info(jobname)
        return self._clean_job_info(info)

    def get_jobs(self) -> list[dict]:
        """Return all jobs visible to the configured user."""
        jobs = self._server.get_jobs()
        cleaned = []
        for name, url, color in jobs:
            try:
                info = self._server.get_job_info(name)
                cleaned.append(self._clean_job_info(info))
            except Exception:
                cleaned.append({"name": name, "url": url, "color": color})
        return cleaned

    def get_build(self, jobname: str, build_number: int | None = None) -> dict:
        """
        Return build metadata — parameters, SCM info (repo, branch, commit),
        and build status.
        """
        if build_number is None:
            info = self._server.get_job_info(jobname)
            build_number = info.get("lastBuild", {}).get("number")
            if build_number is None:
                return {"job": jobname, "error": "No builds found for this job"}

        build_info = self._server.get_build_info(jobname, build_number)

        params = {}
        actions = build_info.get("actions", [])
        for action in actions:
            if "parameters" in action:
                for p in action["parameters"]:
                    params[p.get("name")] = p.get("value")

        repo_url = None
        branch = None
        commit = None
        for action in actions:
            if "lastBuiltRevision" in action:
                revision = action["lastBuiltRevision"]
                commit = revision.get("SHA1")
                branches = revision.get("branch", [])
                if branches:
                    branch = branches[0].get("name")
            if "remoteUrls" in action:
                urls = action.get("remoteUrls", [])
                if urls:
                    repo_url = urls[0]

        return {
            "job": jobname,
            "build_number": build_number,
            "result": build_info.get("result"),
            "url": build_info.get("url"),
            "duration_ms": build_info.get("duration"),
            "timestamp": build_info.get("timestamp"),
            "built_on": build_info.get("builtOn"),
            "parameters": params,
            "repo_url": repo_url,
            "branch": branch,
            "commit": commit,
            "display_name": build_info.get("displayName"),
            "full_display_name": build_info.get("fullDisplayName"),
        }

    def get_build_logs(
        self,
        jobname: str,
        build_number: int | None = None,
        tail_lines: int | None = None,
    ) -> dict:
        """
        Return build console log.  If tail_lines is set, return only the
        last N lines.  If build_number is omitted, use the latest build.
        """
        if build_number is None:
            info = self._server.get_job_info(jobname)
            build_number = info.get("lastBuild", {}).get("number")
            if build_number is None:
                return {"job": jobname, "error": "No builds found"}

        log_text = self._server.get_build_console_output(jobname, build_number)
        lines = log_text.splitlines()
        total = len(lines)

        if tail_lines is not None and tail_lines > 0:
            lines = lines[-tail_lines:]

        return {
            "job": jobname,
            "build_number": build_number,
            "total_lines": total,
            "returned_lines": len(lines),
            "log": "\n".join(lines),
        }

    @staticmethod
    def _clean_job_info(info: dict) -> dict:
        return {
            "name": info.get("name"),
            "url": info.get("url"),
            "color": info.get("color"),
            "description": info.get("description"),
            "display_name": info.get("displayName"),
            "buildable": info.get("buildable"),
            "in_queue": info.get("inQueue"),
            "last_build": _build_summary(info.get("lastBuild")),
            "last_completed_build": _build_summary(info.get("lastCompletedBuild")),
            "last_stable_build": _build_summary(info.get("lastStableBuild")),
            "last_successful_build": _build_summary(info.get("lastSuccessfulBuild")),
            "last_unstable_build": _build_summary(info.get("lastUnstableBuild")),
            "last_failed_build": _build_summary(info.get("lastFailedBuild")),
            "health_score": _health_score(info),
        }


def _build_summary(b: dict | None) -> dict | None:
    if not b:
        return None
    return {
        "number": b.get("number"),
        "url": b.get("url"),
        "result": b.get("result"),
    }


def _health_score(info: dict) -> int | None:
    reports = info.get("healthReport", [])
    if reports:
        return reports[0].get("score")
    return None


# ---------------------------------------------------------------------------
# MCP application
# ---------------------------------------------------------------------------

jenkins_url_display = os.environ.get("JENKINS_URL", "http://localhost:8080")

app = FastMCP(
    name="jenkins",
    instructions=f"""Jenkins MCP server — manage Jenkins jobs and builds.

Server: {jenkins_url_display}

Available tools:
- trigger_build  — Start a build (optionally with parameters)
- stop_build     — Abort a running build
- get_job        — Get detailed job configuration & metadata
- get_jobs       — List all Jenkins jobs
- get_build      — Get build metadata (parameters, SCM info, status)
- get_build_logs — Get build console log (supports tail)
""",
    host="0.0.0.0",
    port=8080,
    log_level="INFO",
)

_client: JenkinsClient | None = None


def _get_client() -> JenkinsClient:
    global _client
    if _client is None:
        _client = JenkinsClient()
    return _client


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@app.tool(description="Trigger a Jenkins build, optionally with build parameters.")
def trigger_build(
    jobname: str,
    params: str | None = None,
) -> str:
    """
    Parameters:
    - jobname: Name of the Jenkins job (e.g. 'my-pipeline')
    - params: Optional JSON string of build parameters
      (e.g. '{"BRANCH":"main","ENV":"prod"}')
    """
    parsed_params: dict | None = None
    if params:
        try:
            parsed_params = json.loads(params)
        except json.JSONDecodeError as e:
            return f"Invalid JSON in params: {e}"

    result = _get_client().trigger_build(jobname, parsed_params)
    return json.dumps(result, indent=2, ensure_ascii=False)


@app.tool(
    description="Stop / abort a running Jenkins build by job name and build number."
)
def stop_build(
    jobname: str,
    build_number: int,
) -> str:
    """
    Parameters:
    - jobname: Name of the Jenkins job
    - build_number: Build number to stop (e.g. 42)
    """
    result = _get_client().stop_build(jobname, build_number)
    return json.dumps(result, indent=2, ensure_ascii=False)


@app.tool(
    description="Get detailed metadata for a Jenkins job (description, health, last builds)."
)
def get_job(
    jobname: str,
) -> str:
    """
    Parameters:
    - jobname: Name of the Jenkins job
    """
    result = _get_client().get_job(jobname)
    return json.dumps(result, indent=2, ensure_ascii=False)


@app.tool(description="List all Jenkins jobs visible to the configured user.")
def get_jobs() -> str:
    """No parameters required."""
    result = _get_client().get_jobs()
    return json.dumps(result, indent=2, ensure_ascii=False)


@app.tool(
    description="Get build metadata: parameters, SCM info (repo/branch/commit), result status."
)
def get_build(
    jobname: str,
    build_number: int | None = None,
) -> str:
    """
    Parameters:
    - jobname: Name of the Jenkins job
    - build_number: Optional build number (omitted -> use latest build)
    """
    result = _get_client().get_build(jobname, build_number)
    return json.dumps(result, indent=2, ensure_ascii=False)


@app.tool(
    description="Get build console log. Optionally return only the last N lines."
)
def get_build_logs(
    jobname: str,
    build_number: int | None = None,
    tail_lines: int | None = None,
) -> str:
    """
    Parameters:
    - jobname: Name of the Jenkins job
    - build_number: Optional build number (omitted -> use latest)
    - tail_lines: Optional - return only the last N lines (e.g. 50)
    """
    result = _get_client().get_build_logs(jobname, build_number, tail_lines)
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("Starting Jenkins MCP Server on 0.0.0.0:8080 (SSE transport)")
    log.info("JENKINS_URL = %s", os.environ.get("JENKINS_URL", "http://localhost:8080"))
    log.info("=" * 60)
    app.run(transport="sse")


if __name__ == "__main__":
    main()
