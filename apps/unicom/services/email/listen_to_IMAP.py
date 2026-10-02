from unicom.services.email.auth_helpers import get_email_service_credentials
from unicom.services.email.save_email_message import save_email_message
from unicom.models import Message
from imapclient import IMAPClient, SEEN
from imapclient.exceptions import IMAPClientError
from django.db import connections
import imaplib
import time
import logging

logger = logging.getLogger(__name__)


def listen_to_IMAP(channel):
    """
    Connects to the IMAP server defined in channel.config and listens via IDLE.
    Fetches new messages and hands them off to save_email_message().
    This runs indefinitely, with automatic reconnects on failure.
    """
    email_address = channel.config['EMAIL_ADDRESS']
    imap_username, imap_password = get_email_service_credentials(channel.config, 'IMAP')
    imap_conf     = channel.config['IMAP']
    host          = imap_conf['host']
    port          = imap_conf['port']
    use_ssl       = imap_conf['use_ssl']

    logger.info(f"Channel {channel.pk}: Starting IMAP listener for {email_address} at {host}:{port} (SSL={use_ssl})")

    while True:
        try:
            with IMAPClient(host, port=port, ssl=use_ssl) as server:
                server.login(imap_username, imap_password)
                server.select_folder('INBOX')
                # caps = server.capabilities()
                mark_seen_on = channel.config.get('mark_seen_on', 'never')
                # Immediately fetch any older unseen messages on startup
                uids = server.search(['UNSEEN'])
                existing_uids = set()
                if uids:
                    existing_uids = set(
                        Message.objects.filter(channel=channel, imap_uid__in=uids).values_list('imap_uid', flat=True)
                    )
                for uid in uids:
                    if uid in existing_uids:
                        continue
                    try:
                        resp = server.fetch(uid, ['BODY.PEEK[]'])
                        raw = resp[uid][b'BODY[]']
                        msg = save_email_message(channel, raw, uid=uid)
                        # logger.info(f"Channel {channel.pk}: Found email {msg.id} (uid={uid})")
                    except Exception as e:
                        logger.error(f"Channel {channel.pk}: Failed to process UID {uid}: {e}")

                if mark_seen_on == 'on_save':
                    if uids:
                        server.add_flags(uids, [SEEN])
                        logger.info(f"Channel {channel.pk}: Marked {len(uids)} messages as SEEN on startup (on_save).")

                logger.info(f"Channel {channel.pk}: Connected to {host}:{port}, entering IDLE…")

                while True:
                    idle_tag = None
                    try:
                        idle_tag = server.idle()
                        responses = server.idle_check(timeout=300)
                    except (imaplib.IMAP4.abort, 
                            imaplib.IMAP4.error, 
                            IMAPClientError,
                            ConnectionResetError, 
                            OSError) as e:
                        if 'Unexpected IDLE response' in str(e) or 'Broken pipe' in str(e) or 'Connection reset by peer' in str(e):
                            break # ignore repeated IDLE errors for now TODO: prevent the error from occuring alltogether
                        logger.warning(f"Channel {channel.pk}: IMAP idle lost: {e}, reconnecting…")
                        break
                    finally:
                        if idle_tag:
                            try:
                                server.idle_done()
                                time.sleep(1)
                            except Exception as e:
                                logger.warning(f"Channel {channel.pk}: Failed to end IDLE: {e}")

                    if not responses:
                        continue

                    uids = server.search(['UNSEEN'])
                    existing_uids = set()
                    if uids:
                        existing_uids = set(
                            Message.objects.filter(channel=channel, imap_uid__in=uids).values_list('imap_uid', flat=True)
                        )
                    for uid in uids:
                        if uid in existing_uids:
                            continue
                        try:
                            resp = server.fetch(uid, ['BODY.PEEK[]'])
                            raw = resp[uid][b'BODY[]']
                            msg = save_email_message(channel, raw, uid=uid)
                            logger.info(f"Channel {channel.pk}: Saved email {msg.id} (uid={uid})")
                            if mark_seen_on == 'on_save':
                                server.add_flags(uid, [SEEN])
                            logger.debug(f"Incoming email - Message-ID: {msg.id}, In-Reply-To: {msg.raw.get('In-Reply-To') if msg.raw else 'None'}")
                            logger.debug(f"Associated with chat: {msg.chat_id}")
                        except Exception:
                            logger.error(f"Channel {channel.pk}: Failed to process UID {uid}")
                        finally:
                            connections.close_all()

        except Exception as e:
            logger.error(f"Channel {channel.pk}: Fatal IMAP error: {e}, reconnecting in 30s…")
            time.sleep(3)
        finally:
            # Ensure we close all connections to avoid leaks
            connections.close_all()
