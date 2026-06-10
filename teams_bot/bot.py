# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import asyncio
import logging
from datetime import datetime

import aiohttp
from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import ChannelAccount

from config import DefaultConfig

logger = logging.getLogger(__name__)
CONFIG = DefaultConfig()

BACKEND_TIMEOUT = aiohttp.ClientTimeout(total=120)


class MyBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        user_text = (turn_context.activity.text or "").strip()
        if not user_text:
            return

        user_id = CONFIG.DEFAULT_USER_ID
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        payload = {
            "text": user_text,
            "user_id": user_id,
            "timestamp": timestamp,
            "is_teams_chat": True,
            "is_related_question": False,
        }

        logger.info("Calling backend  user=%s  text=%r", user_id, user_text)

        try:
            async with aiohttp.ClientSession(timeout=BACKEND_TIMEOUT) as session:
                async with session.post(
                    f"{CONFIG.BACKEND_BASE_URL}/chat",
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        reply_text = data["response"]["message"]["text"]
                        logger.info("Backend responded successfully")
                    else:
                        body = await resp.text()
                        logger.error("Backend returned HTTP %s: %s", resp.status, body)
                        reply_text = (
                            "Sorry, I couldn't get a response right now. Please try again."
                        )

        except asyncio.TimeoutError:
            logger.error("Backend request timed out after %ss", BACKEND_TIMEOUT.total)
            reply_text = "The request took too long. Please try again in a moment."

        except aiohttp.ClientConnectionError as exc:
            logger.error("Connection error reaching backend: %s", exc)
            reply_text = "I'm having trouble connecting to the server. Please try again later."

        except (KeyError, TypeError) as exc:
            logger.error("Unexpected response shape from backend: %s", exc)
            reply_text = "I received an unexpected response. Please try again."

        except Exception as exc:  # noqa: BLE001
            logger.error("Unhandled error: %s", exc, exc_info=True)
            reply_text = "Something went wrong. Please try again."

        await turn_context.send_activity(reply_text)

    async def on_members_added_activity(
        self,
        members_added: ChannelAccount,
        turn_context: TurnContext,
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hello and welcome! How can I help you today?")
