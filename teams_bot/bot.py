# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import asyncio
import json
import logging
from datetime import datetime

import aiohttp
from botbuilder.core import ActivityHandler, CardFactory, MessageFactory, TurnContext
from botbuilder.schema import Activity, ChannelAccount

from config import DefaultConfig

logger = logging.getLogger(__name__)
CONFIG = DefaultConfig()

BACKEND_TIMEOUT = aiohttp.ClientTimeout(total=120)


def _build_response_card(response_text: str, message_id: str, conversation_id: str) -> dict:
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [
            {
                "type": "TextBlock",
                "text": response_text,
                "wrap": True,
            },
        ],
        "actions": [
            {
                "type": "Action.ShowCard",
                "title": "👍",
                "card": {
                    "type": "AdaptiveCard",
                    "version": "1.3",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Great! What did you like about this response?",
                            "wrap": True,
                        },
                        {
                            "type": "Input.Text",
                            "id": "positive_feedback",
                            "placeholder": "Tell us what you liked...",
                            "isMultiline": True,
                        },
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit Feedback",
                            "data": {
                                "actionName": "feedback",
                                "actionValue": {
                                    "reaction": "like",
                                    "message_id": message_id,
                                    "conversation_id": conversation_id,
                                    "original_response": response_text,
                                    "feedback_type": "detailed",
                                },
                            },
                        }
                    ],
                },
            },
            {
                "type": "Action.ShowCard",
                "title": "👎",
                "card": {
                    "type": "AdaptiveCard",
                    "version": "1.3",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Sorry to hear that. How can we improve?",
                            "wrap": True,
                        },
                        {
                            "type": "Input.Text",
                            "id": "negative_feedback",
                            "placeholder": "Tell us how we can improve...",
                            "isMultiline": True,
                        },
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit Feedback",
                            "data": {
                                "actionName": "feedback",
                                "actionValue": {
                                    "reaction": "dislike",
                                    "message_id": message_id,
                                    "conversation_id": conversation_id,
                                    "original_response": response_text,
                                    "feedback_type": "detailed",
                                },
                            },
                        }
                    ],
                },
            },
        ],
    }


def _build_feedback_received_card(response_text: str, reaction: str) -> dict:
    emoji = "👍" if reaction == "like" else "👎"
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [
            {
                "type": "TextBlock",
                "text": response_text,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"Feedback submitted {emoji}",
                "wrap": True,
                "isSubtle": True,
                "size": "Small",
            },
        ],
    }


async def _send_feedback_to_backend(value: dict) -> None:
    action_value = value.get("actionValue", {})
    positive = action_value.get("reaction") == "like"
    reason = value.get("positive_feedback" if positive else "negative_feedback") or ""

    payload = {
        "conversation_id": action_value.get("conversation_id", ""),
        "feedback_time": datetime.now().isoformat(),
        "message_id": action_value.get("message_id", ""),
        "positive": positive,
        "reason": reason,
        "user_id": CONFIG.DEFAULT_USER_ID,
    }

    logger.info("Sending feedback: %s", json.dumps(payload))

    headers = {"x-api-key": CONFIG.GATEWAY_API_KEY}

    try:
        async with aiohttp.ClientSession(timeout=BACKEND_TIMEOUT) as session:
            async with session.post(
                f"{CONFIG.BACKEND_BASE_URL}/message_feedback",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status == 201:
                    logger.info("Feedback submitted successfully")
                else:
                    body = await resp.text()
                    logger.error(
                        "Feedback backend returned HTTP %s: %s", resp.status, body
                    )
    except Exception as exc:  # noqa: BLE001
        logger.error("Error sending feedback: %s", exc, exc_info=True)


class MyBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        # Handle Adaptive Card submissions
        if turn_context.activity.value:
            value = turn_context.activity.value
            if isinstance(value, dict) and value.get("actionName") == "feedback":
                await _send_feedback_to_backend(value)

                activity_id = turn_context.activity.reply_to_id
                if activity_id:
                    action_value = value.get("actionValue", {})
                    updated_card = _build_feedback_received_card(
                        action_value.get("original_response", ""),
                        action_value.get("reaction", ""),
                    )
                    updated_activity = Activity(
                        id=activity_id,
                        type="message",
                        attachments=[CardFactory.adaptive_card(updated_card)],
                    )
                    try:
                        await turn_context.update_activity(updated_activity)
                    except Exception as exc:
                        logger.error("Failed to update card: %s", exc)

                await turn_context.send_activity("Thank you for your feedback!")
            else:
                logger.info("Received card submission: %s", json.dumps(value))
            return

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

        message_id = ""
        conversation_id = ""

        try:
            async with aiohttp.ClientSession(timeout=BACKEND_TIMEOUT) as session:
                async with session.post(
                    f"{CONFIG.BACKEND_BASE_URL}/chat",
                    json=payload,
                    headers={"x-api-key": CONFIG.GATEWAY_API_KEY},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        response_data = data["response"]
                        reply_text = response_data["message"]["text"]
                        message_id = response_data.get("message_id", "")
                        conversation_id = response_data.get("conversation_id", "")
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

        card = _build_response_card(reply_text, message_id, conversation_id)
        attachment = CardFactory.adaptive_card(card)
        await turn_context.send_activity(MessageFactory.attachment(attachment))

    async def on_members_added_activity(
        self,
        members_added: ChannelAccount,
        turn_context: TurnContext,
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hello and welcome! How can I help you today?")
