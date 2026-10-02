# import time
# import logging
# from imapclient import IMAPClient, SEEN
# from django.core.management.base import BaseCommand
# from django.conf import settings

# from robopower.services.email.save_email_message import save_email_message

# logger = logging.getLogger(__name__)

# class Command(BaseCommand):
#     help = "Listen to an IMAP account via IDLE and hand off new emails."

#     def handle(self, *args, **options):
#         while True:
#             try:
#                 with IMAPClient(settings.IMAP_HOST, port=settings.IMAP_PORT, ssl=settings.IMAP_USE_SSL) as server:
#                     print(f"Logging in to {settings.IMAP_HOST}:{settings.IMAP_PORT} as {settings.IMAP_USER} with pwd {settings.IMAP_PASSWORD}")
#                     server.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
#                     server.select_folder('INBOX')
#                     self.stdout.write("✅ Connected to IMAP, entering IDLE…")

#                     while True:
#                         try:
#                             server.idle()                             # enter IDLE
#                             responses = server.idle_check(timeout=300)  # wake up at least every 5m
#                         except (ConnectionResetError, OSError) as e:
#                             logger.warning("IMAP idle connection lost: %s", e)
#                             break  # break inner loop to reconnect
#                         finally:
#                             # if idle() succeeded we need to terminate it
#                             # (noop if connection already gone)
#                             try:
#                                 server.idle_done()
#                             except Exception:
#                                 pass

#                         if not responses:
#                             continue

#                         # process all new unseen messages
#                         uids = server.search(['UNSEEN'])
#                         for uid in uids:
#                             try:
#                                 resp = server.fetch(uid, ['BODY.PEEK[]'])
#                                 raw = resp[uid][b'BODY[]']
#                                 msg = save_email_message(raw)
#                                 self.stdout.write(f"💾 Saved email {msg.id} (uid={uid})")
#                                 server.add_flags(uid, [SEEN])
#                             except Exception as exc:
#                                 logger.exception("Failed to process UID %s: %s", uid, exc)

#             except Exception as e:
#                 logger.exception("Fatal IMAP error, reconnecting in 30s…")
#                 time.sleep(30)
