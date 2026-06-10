#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import os


class DefaultConfig:
    """Bot Configuration"""

    PORT = int(os.environ.get("PORT", 3978))
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    BACKEND_BASE_URL = os.environ.get(
        "BACKEND_BASE_URL",
        "https://gqf4f2pds1.execute-api.eu-central-1.amazonaws.com/dev",
    )
    DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "jitendrakushwah@bitcot.com")
    GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY", "")
