from typing import Any, Optional

import discord

from discord_mcp.mcp.context import get_current_session, update_bot_status, clear_bot_status
from discord_mcp.utils.logging import get_logger

logger = get_logger(__name__)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg")


def _serialize_attachment(attachment: discord.Attachment) -> dict[str, Any]:
    return {
        "id": str(attachment.id),
        "filename": attachment.filename,
        "url": attachment.url,
        "content_type": attachment.content_type,
        "size": attachment.size,
    }


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    if attachment.content_type and attachment.content_type.startswith("image/"):
        return True
    return attachment.filename.lower().endswith(IMAGE_EXTENSIONS)


async def _resolve_channel(client: discord.Client, channel_id: str):
    """Find a channel or thread by id.

    The cache only holds channels and the active threads of guilds the bot can
    see, so an archived thread is fetched from the API instead.
    """
    channel = client.get_channel(int(channel_id))
    if channel is not None:
        return channel
    try:
        return await client.fetch_channel(int(channel_id))
    except (discord.NotFound, discord.Forbidden):
        return None


async def _with_status(activity: str):
    """Helper to update bot status."""
    await update_bot_status(activity, "playing")


def _handle_discord_error(e: discord.HTTPException) -> None:
    """Handle common Discord HTTP errors."""
    if isinstance(e, discord.Forbidden):
        error_code = getattr(e, "code", None)
        if error_code == 50013:
            from discord_mcp.discord.exceptions import MessageException

            raise MessageException(
                "Bot lacks required permissions. Please ensure the bot has the necessary permissions in Discord server settings.",
                details={"error_code": error_code, "original_error": str(e)},
            )
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Permission denied: {str(e)}",
            details={"error_code": error_code, "original_error": str(e)},
        )
    elif isinstance(e, discord.NotFound):
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            "Message not found",
            details={"original_error": str(e)},
        )


async def send_message(
    channel_id: str,
    content: str,
    tts: bool = False,
    embeds: Optional[list[dict[str, Any]]] = None,
    allowed_mentions: Optional[dict[str, list[str]]] = None,
    message_reference: Optional[dict[str, str]] = None,
    components: Optional[list[dict[str, Any]]] = None,
    file_path: Optional[str] = None,
) -> dict[str, Any]:
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = client.get_channel(int(channel_id))
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    if not isinstance(channel, (discord.TextChannel, discord.DMChannel, discord.GroupChannel)):
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} is not a text channel",
            details={"channel_id": channel_id, "type": channel.type},
        )

    embed_objects = None
    if embeds:
        embed_objects = [discord.Embed.from_dict(e) for e in embeds]

    allowed_mentions_obj = None
    if allowed_mentions:
        allowed_mentions_obj = discord.AllowedMentions(
            everyone=allowed_mentions.get("everyone", False),
            users=allowed_mentions.get("users", []),
            roles=allowed_mentions.get("roles", []),
        )

    reference = None
    if message_reference:
        reference = discord.MessageReference(
            message_id=int(message_reference.get("message_id")),
            channel_id=int(message_reference.get("channel_id", channel_id)),
            guild_id=int(message_reference.get("guild_id"))
            if message_reference.get("guild_id")
            else None,
        )

    # Components need special handling - skip for now to avoid errors
    send_kwargs: dict[str, Any] = {
        "content": content,
        "tts": tts,
        "allowed_mentions": allowed_mentions_obj,
        "reference": reference,
    }

    if embeds:
        if len(embeds) == 1:
            send_kwargs["embed"] = embed_objects[0]
        else:
            send_kwargs["embeds"] = embed_objects

    if file_path:
        import os

        if not os.path.isfile(file_path):
            from discord_mcp.discord.exceptions import MessageException

            raise MessageException(
                f"File not found: {file_path}",
                details={"file_path": file_path},
            )
        send_kwargs["file"] = discord.File(file_path)

    message = await channel.send(**send_kwargs)

    await update_bot_status(f"Sending message", "playing")

    logger.info("message_sent", message_id=str(message.id), channel_id=channel_id)

    return {
        "id": str(message.id),
        "channel_id": str(message.channel.id),
        "content": message.content,
        "author": {
            "id": str(message.author.id),
            "username": message.author.name,
            "discriminator": message.author.discriminator,
        },
        "timestamp": message.created_at.isoformat(),
    }


async def edit_message(
    channel_id: str,
    message_id: str,
    content: Optional[str] = None,
    embeds: Optional[list[dict[str, Any]]] = None,
    flags: Optional[int] = None,
    allowed_mentions: Optional[dict[str, list[str]]] = None,
    components: Optional[list[dict[str, Any]]] = None,
    remove_attachment_ids: Optional[list[str]] = None,
    add_file_paths: Optional[list[str]] = None,
) -> dict[str, Any]:
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = client.get_channel(int(channel_id))
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Message {message_id} not found",
            details={"message_id": message_id},
        )

    embed_objects = None
    if embeds:
        embed_objects = [discord.Embed.from_dict(e) for e in embeds]

    allowed_mentions_obj = None
    if allowed_mentions:
        allowed_mentions_obj = discord.AllowedMentions(
            everyone=allowed_mentions.get("everyone", False),
            users=allowed_mentions.get("users", []),
            roles=allowed_mentions.get("roles", []),
        )

    component_objects = None
    if components:
        component_objects = [discord.Component.from_dict(c) for c in components]

    kwargs: dict[str, Any] = {}
    if content is not None:
        kwargs["content"] = content
    if embed_objects is not None:
        kwargs["embeds"] = embed_objects
    if flags is not None:
        kwargs["flags"] = discord.MessageFlags(flags)
    if allowed_mentions_obj is not None:
        kwargs["allowed_mentions"] = allowed_mentions_obj
    if component_objects is not None:
        kwargs["components"] = component_objects

    if remove_attachment_ids is not None or add_file_paths is not None:
        import os

        remove_ids = {str(a) for a in (remove_attachment_ids or [])}
        kept_attachments = [a for a in message.attachments if str(a.id) not in remove_ids]

        new_files = []
        for file_path in add_file_paths or []:
            if not os.path.isfile(file_path):
                from discord_mcp.discord.exceptions import MessageException

                raise MessageException(
                    f"File not found: {file_path}",
                    details={"file_path": file_path},
                )
            new_files.append(discord.File(file_path))

        kwargs["attachments"] = [*kept_attachments, *new_files]

    message = await message.edit(**kwargs)

    await _with_status(f"Editing message")
    logger.info("message_edited", message_id=message_id, channel_id=channel_id)

    return {
        "id": str(message.id),
        "channel_id": str(message.channel.id),
        "content": message.content,
        "attachments": [_serialize_attachment(a) for a in message.attachments],
        "edited_timestamp": message.edited_at.isoformat() if message.edited_at else None,
    }


async def delete_message(
    channel_id: str, message_id: str, guild_id: Optional[str] = None
) -> dict[str, Any]:
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = client.get_channel(int(channel_id))
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Message {message_id} not found",
            details={"message_id": message_id},
        )

    await message.delete()

    await _with_status(f"Deleting message")
    logger.info("message_deleted", message_id=message_id, channel_id=channel_id)

    return {
        "success": True,
        "message_id": message_id,
        "channel_id": channel_id,
    }


async def bulk_delete_messages(
    channel_id: str,
    messages: list[str],
    guild_id: Optional[str] = None,
) -> dict[str, Any]:
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = client.get_channel(int(channel_id))
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    if not isinstance(channel, discord.TextChannel):
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} is not a text channel",
            details={"channel_id": channel_id},
        )

    message_ids = [int(m) for m in messages]
    deleted = await channel.purge(limit=len(messages), check=lambda m: m.id in message_ids)

    await _with_status(f"Bulk deleting messages")
    logger.info("messages_bulk_deleted", count=len(deleted), channel_id=channel_id)

    return {
        "success": True,
        "deleted_count": len(deleted),
        "channel_id": channel_id,
    }


async def get_message(channel_id: str, message_id: str) -> dict[str, Any]:
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = await _resolve_channel(client, channel_id)
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    try:
        message = await channel.fetch_message(int(message_id))
    except discord.NotFound:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Message {message_id} not found",
            details={"message_id": message_id},
        )

    return {
        "id": str(message.id),
        "channel_id": str(message.channel.id),
        "content": message.content,
        "author": {
            "id": str(message.author.id),
            "username": message.author.name,
            "discriminator": message.author.discriminator,
        },
        "timestamp": message.created_at.isoformat(),
        "edited_timestamp": message.edited_at.isoformat() if message.edited_at else None,
        "tts": message.tts,
        "mention_everyone": message.mention_everyone,
        "mentions": [str(m.id) for m in message.mentions],
        "channel_mentions": [str(c.id) for c in message.channel_mentions],
        "attachments": [_serialize_attachment(a) for a in message.attachments],
        "pinned": message.pinned,
    }


MAX_HISTORY_MESSAGES = 5000


async def get_channel_messages(
    channel_id: str,
    limit: Optional[int] = 50,
    before: Optional[str] = None,
    after: Optional[str] = None,
    oldest_first: bool = False,
) -> list[dict[str, Any]]:
    """Read messages of a text channel, a DM or a thread (active or archived).

    limit=None reads everything (discord.py pages through the API 100 messages
    at a time); a number is capped at MAX_HISTORY_MESSAGES. Newest first unless
    oldest_first is set; with `after` the history already runs oldest first.
    """
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = await _resolve_channel(client, channel_id)
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    if not isinstance(channel, (discord.TextChannel, discord.DMChannel, discord.Thread)):
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} is not a text channel or a thread",
            details={"channel_id": channel_id},
        )

    before_msg = None
    after_msg = None
    if before:
        before_msg = await channel.fetch_message(int(before))
    if after:
        after_msg = await channel.fetch_message(int(after))

    effective_limit = None if limit is None else max(0, min(limit, MAX_HISTORY_MESSAGES))

    messages = []
    async for message in channel.history(
        limit=effective_limit,
        before=before_msg,
        after=after_msg,
        oldest_first=oldest_first or None,
    ):
        messages.append(
            {
                "id": str(message.id),
                "channel_id": str(message.channel.id),
                "content": message.content,
                "author": {
                    "id": str(message.author.id),
                    "username": message.author.name,
                    "discriminator": message.author.discriminator,
                },
                "timestamp": message.created_at.isoformat(),
                "edited_timestamp": message.edited_at.isoformat() if message.edited_at else None,
                "reply_to": (
                    str(message.reference.message_id)
                    if message.reference and message.reference.message_id
                    else None
                ),
                "type": message.type.name,
                "attachments": [_serialize_attachment(a) for a in message.attachments],
                "pinned": message.pinned,
            }
        )

    return messages


async def download_channel_attachments(
    channel_id: str,
    save_dir: str,
    limit: Optional[int] = 100,
    before: Optional[str] = None,
    after: Optional[str] = None,
    images_only: bool = True,
) -> dict[str, Any]:
    session = await get_current_session()
    client = session.client

    if not client:
        from discord_mcp.discord.exceptions import SessionException

        raise SessionException("Client not initialized")

    channel = await _resolve_channel(client, channel_id)
    if not channel:
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} not found",
            details={"channel_id": channel_id},
        )

    if not isinstance(channel, (discord.TextChannel, discord.DMChannel, discord.Thread)):
        from discord_mcp.discord.exceptions import MessageException

        raise MessageException(
            f"Channel {channel_id} is not a text channel or a thread",
            details={"channel_id": channel_id},
        )

    import os

    os.makedirs(save_dir, exist_ok=True)

    before_msg = None
    after_msg = None
    if before:
        before_msg = await channel.fetch_message(int(before))
    if after:
        after_msg = await channel.fetch_message(int(after))

    downloaded: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped = 0

    async for message in channel.history(limit=limit, before=before_msg, after=after_msg):
        for attachment in message.attachments:
            if images_only and not _is_image_attachment(attachment):
                skipped += 1
                continue

            safe_filename = os.path.basename(attachment.filename)
            dest_path = os.path.join(save_dir, f"{message.id}_{attachment.id}_{safe_filename}")

            try:
                await attachment.save(dest_path)
            except discord.HTTPException as e:
                errors.append(
                    {
                        "message_id": str(message.id),
                        "attachment_id": str(attachment.id),
                        "filename": attachment.filename,
                        "error": str(e),
                    }
                )
                continue

            downloaded.append(
                {
                    "message_id": str(message.id),
                    "attachment_id": str(attachment.id),
                    "filename": attachment.filename,
                    "saved_path": dest_path,
                    "size": attachment.size,
                    "content_type": attachment.content_type,
                }
            )

    await _with_status("Downloading channel attachments")
    logger.info(
        "channel_attachments_downloaded",
        channel_id=channel_id,
        downloaded_count=len(downloaded),
        skipped_count=skipped,
        error_count=len(errors),
    )

    return {
        "success": True,
        "channel_id": channel_id,
        "save_dir": save_dir,
        "downloaded_count": len(downloaded),
        "skipped_count": skipped,
        "files": downloaded,
        "errors": errors,
    }
