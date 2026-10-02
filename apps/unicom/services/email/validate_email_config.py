import imaplib
import smtplib
import dns.resolver
from django.core.exceptions import ValidationError
import requests, xml.etree.ElementTree as ET

from .auth_helpers import get_email_service_credentials


def get_srv_candidates(service: str, domain: str):
    try:
        print(f"Querying DNS SRV records for {service} on {domain}")
        answers = dns.resolver.resolve(f"_{service}._tcp.{domain}", "SRV")
        return [
            {"host": str(r.target).rstrip("."), "port": r.port}
            for r in answers
        ]
    except Exception:
        return []

def validate_imap(config: dict, email_address: str, password: str):
    try:
        if config['use_ssl']:
            conn = imaplib.IMAP4_SSL(config['host'], config['port'], timeout=10)
        else:
            conn = imaplib.IMAP4(config['host'], config['port'], timeout=10)
        conn.login(email_address, password)
        conn.logout()
        return True
    except Exception as e:
        print(f"IMAP connection failed: {e}")
        return False

def validate_smtp(config: dict, email_address: str, password: str):
    try:
        if config['use_ssl']:
            smtp = smtplib.SMTP_SSL(config['host'], config['port'], timeout=10)
        else:
            smtp = smtplib.SMTP(config['host'], config['port'], timeout=10)
            smtp.starttls()
        smtp.login(email_address, password)
        smtp.quit()
        return True
    except Exception as e:
        print(f"SMTP connection failed: {e}")
        return False


def get_config_using_mozilla(domain: str) -> dict:
    # ─── TRY MOZILLA ISPDB (AUTOCONFIG) ──────────────────────────────
    # If the domain is in Mozilla’s ISPDB, fetch its XML and return it.
    print(f"Trying Mozilla ISPDB for {domain}")
    try:
        url = f"https://autoconfig.thunderbird.net/v1.1/{domain}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            tree = ET.fromstring(r.content)
            imap_node = tree.find('.//incomingServer[@type="imap"]')
            smtp_node = tree.find('.//outgoingServer[@type="smtp"]')
            print(f"Mozilla ISPDB response for {domain}: imap_node={imap_node}, smtp_node={smtp_node}")
            if imap_node is not None and smtp_node is not None:
                return {
                    "IMAP": {
                        "host":     imap_node.findtext('hostname'),
                        "port":     int(imap_node.findtext('port')),
                        "use_ssl":  imap_node.findtext('socketType').lower().startswith('ssl'),
                        "protocol": "IMAP"
                    },
                    "SMTP": {
                        "host":     smtp_node.findtext('hostname'),
                        "port":     int(smtp_node.findtext('port')),
                        "use_ssl":  smtp_node.findtext('socketType').lower().startswith('ssl'),
                        "protocol": "SMTP"
                    }
                }
        else:
            print(f"Mozilla ISPDB returned non-200 status for {domain}: {r.status_code}, {r.text}")
    except Exception:
        pass


def detect_email_servers(
    email_address: str,
    imap_username: str,
    imap_password: str,
    smtp_username: str,
    smtp_password: str,
) -> dict:
    """
    Attempt to autodetect IMAP and SMTP server settings based on email domain.
    Returns a dict: {'IMAP': {...}, 'SMTP': {...}}
    """
    domain = email_address.split('@')[-1]
    print(f"Detecting email servers for {email_address} (domain: {domain})")
    # 1. Try Mozilla ISPDB first
    config = get_config_using_mozilla(domain)
    if config:
        print(f"Found Mozilla ISPDB config for {domain}: {config} now validating")
        if validate_imap(config['IMAP'], imap_username, imap_password) and validate_smtp(config['SMTP'], smtp_username, smtp_password):
            print(f"Validated ISPDB config for {domain}")
            return config
        else:
            raise ValidationError(f"Found valid config but authentication failed for {domain}")
    # 2. If not found, try DNS SRV records and MX records
    mx_hosts = []
    try:
        print(f"Querying MX records for {domain}")
        answers = dns.resolver.resolve(domain, 'MX')
        print(f"Found {len(answers)} MX records for {domain}")
        # sort by preference
        sorted_mx = sorted(answers, key=lambda r: r.preference)
        mx_hosts = [str(r.exchange).rstrip('.') for r in sorted_mx]
    except Exception:
        mx_hosts = []
    # build candidate list from MX hosts + generic prefixes
    candidates = []
    candidates += [
        {**c, "protocol": "IMAP",  "use_ssl": True}
        for c in get_srv_candidates("imaps", domain)
    ]
    candidates += [
        {**c, "protocol": "SMTP", "use_ssl": False}
        for c in get_srv_candidates("submission", domain)
    ]
    for mx in mx_hosts:
        print(f"Processing MX host: {mx}")
        config = get_config_using_mozilla(mx)  # try ISPDB for MX host
        if config:
            print(f"Found Mozilla ISPDB config for MX {mx}: {config} now validating")
            if validate_imap(config['IMAP'], imap_username, imap_password) and validate_smtp(config['SMTP'], smtp_username, smtp_password):
                print(f"Validated ISPDB config for MX {mx}")
                return config
            else:
                raise ValidationError(f"Found valid config but authentication failed for MX {mx}")
        # try SRV records for MX host
        candidates += [
            {**c, "protocol": "IMAP",  "use_ssl": True}
            for c in get_srv_candidates("imaps", mx)
        ]
        candidates += [
            {**c, "protocol": "SMTP", "use_ssl": False}
            for c in get_srv_candidates("submission", mx)
        ]
        candidates += [
            {'host': mx,                          'port': 993, 'use_ssl': True,  'protocol': 'IMAP'},
            {'host': mx,                          'port': 465, 'use_ssl': True,  'protocol': 'SMTP'},
            {'host': mx,                          'port': 587, 'use_ssl': False, 'protocol': 'SMTP'},
        ]
        # try imap./smtp. prefixes on MX domain
        base = mx.split('.', 1)[-1]  # e.g. 'google.com' from 'aspmx.l.google.com'
        print(f"Using base domain for MX {mx}: {base}")
        config = get_config_using_mozilla(base)  # try ISPDB for base domain
        if config:
            print(f"Found Mozilla ISPDB config for base {base}: {config} now validating")
            if validate_imap(config['IMAP'], imap_username, imap_password) and validate_smtp(config['SMTP'], smtp_username, smtp_password):
                print(f"Validated ISPDB config for base {base}")
                return config
            else:
                raise ValidationError(f"Found valid config but authentication failed for base {base}")
        # add generic candidates for MX base domain
        print(f"Adding generic candidates for base domain {base}")
        candidates += [
            {'host': f'imap.{base}',            'port': 993, 'use_ssl': True,  'protocol': 'IMAP'},
            {'host': f'mail.{base}',            'port': 993, 'use_ssl': True,  'protocol': 'IMAP'},
            {'host': f'smtp.{base}',            'port': 587, 'use_ssl': False, 'protocol': 'SMTP'},
            {'host': f'smtp.{base}',            'port': 465, 'use_ssl': True,  'protocol': 'SMTP'},
        ]

    # 2. still include the plain domain-based guesses last
    candidates += [
        {'host': f'imap.{domain}', 'port': 993, 'use_ssl': True,  'protocol': 'IMAP'},
        {'host': f'mail.{domain}', 'port': 993, 'use_ssl': True,  'protocol': 'IMAP'},
        {'host': f'smtp.{domain}', 'port': 587, 'use_ssl': False, 'protocol': 'SMTP'},
        {'host': f'smtp.{domain}', 'port': 465, 'use_ssl': True,  'protocol': 'SMTP'},
    ]
    config = {'IMAP': None, 'SMTP': None}

    # Test IMAP servers
    for cand in [c for c in candidates if c['protocol'] == 'IMAP']:
        try:
            print(f"Testing IMAP server: {cand['host']}:{cand['port']} (SSL: {cand['use_ssl']})")
            if validate_imap(cand, imap_username, imap_password):
                config['IMAP'] = cand
                print(f"IMAP server {cand['host']}:{cand['port']} is reachable")
                break
        except Exception as e:
            print(f"IMAP server {cand['host']}:{cand['port']} failed: {e}")
            continue
    if not config['IMAP']:
        raise ValidationError(
            "Unable to auto-detect IMAP settings. "
            "Please provide explicit IMAP block."
        )

    # Test SMTP servers
    for cand in [c for c in candidates if c['protocol'] == 'SMTP']:
        print(f"Testing SMTP server: {cand['host']}:{cand['port']} (SSL: {cand['use_ssl']})")
        try:
            if validate_smtp(cand, smtp_username, smtp_password):
                config['SMTP'] = cand
                print(f"SMTP server {cand['host']}:{cand['port']} is reachable")
                break
        except Exception as e:
            print(f"SMTP server {cand['host']}:{cand['port']} failed: {e}")
            continue

    if not config['IMAP'] or not config['SMTP']:
        raise ValidationError(
            "Unable to auto-detect IMAP/SMTP settings. "
            "Please provide explicit IMAP{} and SMTP{} blocks."
            .format('', '')
        )
    print(f"Detected IMAP: {config['IMAP']}, SMTP: {config['SMTP']}")
    return config


def validate_email_config(config: dict) -> dict:
    """
    Validate and normalize an email configuration dict. Accepts:
      {
        "EMAIL_ADDRESS": str,
        "EMAIL_PASSWORD": str,
        # Optional explicit server blocks:
        "IMAP": {"HOST": str, "PORT": int, "USE_SSL": bool},
        "SMTP": {"HOST": str, "PORT": int, "USE_SSL": bool}
      }
    Returns a dict with normalized IMAP/SMTP blocks added.
    Raises ValidationError on failure.
    """
    address = config.get('EMAIL_ADDRESS')
    password = config.get('EMAIL_PASSWORD')
    if not address or not password:
        raise ValidationError('Both EMAIL_ADDRESS and EMAIL_PASSWORD are required.')

    imap_conf = config.get('IMAP')
    smtp_conf = config.get('SMTP')
    imap_username, imap_password = get_email_service_credentials(config, 'IMAP')
    smtp_username, smtp_password = get_email_service_credentials(config, 'SMTP')

    # If explicit settings provided, test them
    if imap_conf and smtp_conf:
        try:
            if imap_conf.get("use_ssl", True):
                conn = imaplib.IMAP4_SSL(imap_conf['host'], imap_conf['port'])
            else:
                conn = imaplib.IMAP4(imap_conf['host'], imap_conf['port'])
            conn.login(imap_username, imap_password)
            conn.logout()

            if smtp_conf.get("use_ssl", True):
                smtp = smtplib.SMTP_SSL(smtp_conf['host'], smtp_conf['port'])
            else:
                smtp = smtplib.SMTP(smtp_conf['host'], smtp_conf['port'])
                smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.quit()
        except Exception as e:
            raise ValidationError(f'Provided server settings invalid: {e}')
        return {**config, 'IMAP': imap_conf, 'SMTP': smtp_conf}

    # Otherwise autodetect
    print(f"Autodetecting email servers for {address}")
    detected = detect_email_servers(
        address,
        imap_username,
        imap_password,
        smtp_username,
        smtp_password,
    )
    return {**config, **detected}
