"""Hosting signals supplement, never replace, request and ownership verification."""
import os


def hosted_runtime():
    return any(os.environ.get(name) for name in (
        "RENDER", "RENDER_SERVICE_ID", "CONTAINER_APP_NAME", "CONTAINER_APP_REVISION", "WEBSITE_INSTANCE_ID"
    ))
