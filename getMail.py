#! /usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import time
import email
import poplib
import imaplib
import cStringIO
from hashlib import md5


# Configuration
# -------------

# Email address
MAILADDR = "jiayuan_test@126.com"

# Email password
PASSWORD = "jiayuan"

# Mail Server (pop/imap)
SERVER = "imap.126.com"

# Transfer protocol (pop3/imap4)
PROTOCOL = "imap"

# Use SSL? (True/False)
USE_SSL = True

# Main output direcotory
OUTDIR = "result"


# Static variable
# ---------------

# Default port of each protocol
DEFAULT_PORT = {
    "pop3": {False: 110, True: 995},
    "imap4": {False: 143, True: 993},
}


# Function
# --------

def exit_script(reason, e=""):
    """Print error reason and exit this script
    
    :param reason: exit error reason
    :param e: exception
    """
    # Print exit string
    exit_str = "[-] {0}".format(reason)
    if e:
        exit_str += " ({0})".format(e)
    print(exit_str)
    
    # Remove result path
    remove_dir(result_path)
    
    # Exit script
    print("[-] Fetch email failed!")
    exit(-1)

def parse_protocol(protocol):
    """Parse transfer protocol
    
    :param protocol: transfer protocol
    :return: handled protocol
    """
    if protocol in ["pop", "pop3"]:
        return "pop3"
    elif protocol in ["imap", "imap4"]:
        return "imap4"
    else:
        exit_script("Parse protocol failed: {0}".format(protocol))

def parse_server(server, use_ssl, protocol):
    """Change server to host and port. If no port specified, use default value
    
    :param server: mail server (host, host:port)
    :param use_ssl: True if use SSL else False
    :param protocol: transfer protocol (pop3/imap4)
    :return: host and port
    """
    if not server:
        exit_script("No available server")
    
    server_item = server.split(":")
    server_item_len = len(server_item)
    
    if server_item_len > 2:
        exit_script("Too many colons in server: {0}".format(server))
    
    try:
        host = server_item[0]
        port = DEFAULT_PORT[protocol][use_ssl] if server_item_len == 1 else int(server_item[1])
    except BaseException as e:
        exit_script("Parse server format failed: {0}".format(server), e)
    return host, port

def create_dir(result_path):
    """Create output directory if not exist
    
    :param result_path: main result path
    """
    try:
        if not os.path.exists(result_path):
            os.makedirs(result_path)
            print("[*] Create directory {0} successfully".format(result_path))
        else:
            if os.path.isfile(result_path):
                exit_script("{0} is file".format(result_path))
            else:
                print("[*] Directory {0} has already existed".format(result_path))
    except BaseException as e:
        exit_script("Create directory {0} failed".format(result_path), e)

def remove_dir(result_path):
    """Remove output directory if no file in this directory
    
    :param result_path: main result path
    """
    try:
        if os.path.isdir(result_path):
            if len(os.listdir(result_path)) == 0:
                os.rmdir(result_path)
                print("[*] Remove directory {0} successfully".format(result_path))
            else:
                print("[*] Directory {0} is not empty, no need remove".format(result_path))
        else:
            print("[*] No directory {0}".format(result_path))
    except BaseException as e:
        print("[-] Remove directory {0} failed: {1}".format(result_path, e))

def protocol_manager(protocol, host, port, usr, pwd, use_ssl):
    """Choose handle function according to transfer protocol
    
    :param protocol: transfer protocol (pop3/imap4)
    :param host: host
    :param port: port
    :param usr: username
    :param pwd: password
    :param use_ssl: True if use ssl else False
    """
    import __main__
    if hasattr(__main__, protocol):
        getattr(__main__, protocol)(host, port, usr, pwd, use_ssl)
    else:
        exit_script("Wrong protocol: {0}".format(protocol))

def pop3(host, port, usr, pwd, use_ssl):
    """Pop3 handler
    
    :param host: host
    :param port: port
    :param usr: username
    :param pwd: password
    :param use_ssl: True if use SSL else False
    """
    # Connect to mail server
    try:
        conn = poplib.POP3_SSL(host, port) if use_ssl else poplib.POP3(host, port)
        conn.user(usr)
        conn.pass_(pwd)
        print("[+] Connect to {0}:{1} successfully".format(host, port))
        print('[+] Messages: %s. Size: %s' % conn.stat())
    except BaseException as e:
        exit_script("Connect to {0}:{1} failed".format(host, port), e)
    
    # Get email message number
    try:
        msg_num = len(conn.list()[1])

        print("[*] {0} emails found in {1}".format(msg_num, usr))
    except BaseException as e:
        exit_script("Can't get email number", e)

    # Get email content and attachments
    for i in range(1, msg_num+1):
        print("[*] Downloading email {0}/{1}".format(i, msg_num))
        
        # Retrieve email message lines, and write to buffer
        try:
            msg_lines = conn.retr(i)[1]
            
            buf = cStringIO.StringIO()
            for line in msg_lines:
                print >> buf, line
            buf.seek(0)
        except BaseException as e:
            print "[-] Retrieve email {0} failed: {1}".format(i, e)
            continue
        
        # Read buffer
        try:
            msg = email.message_from_file(buf)
        except BaseException as e:
            print "[-] Read buffer of email {0} failed: {1}".format(i, e)
            continue
        
        # Parse and save email content/attachments
        try:
            parse_email(msg, i)
        except BaseException as e:
            print("[-] Parse email {0} failed: {1}".format(i, e))
    
    # Quit mail server
    conn.quit()
    
def imap4(host, port, usr, pwd, use_ssl):
    """Imap4 handler
    
    :param host: host
    :param port: port
    :param usr: username
    :param pwd: password
    :param use_ssl: True if use SSL else False
    """
    # Connect to mail server
    try:
        conn = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        conn.login(usr, pwd)
        print("[+] Connect to {0}:{1} successfully".format(host, port))
    except BaseException as e:
        exit_script("Connect to {0}:{1} failed".format(host, port), e)
    
    # Initial some variable
    list_pattern = re.compile(r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)')
    download_num = 0
    download_hash = []
    
    # Get all folders
    try:
        type_, folders = conn.list()
    except BaseException as e:
        exit_script("Get folder list failed", e)
    
    for folder in folders:
        # Parse folder info and get folder name
        try:
            flags, delimiter, folder_name = list_pattern.match(folder).groups()
            folder_name = folder_name.strip('"')
            print "[*] Handling folder: {0}".format(folder_name)
        except BaseException as e:
            print "[-] Parse folder {0} failed: {1}".format(folder, e)
            continue
        
        # Select and search folder
        try:
            conn.select(folder_name, readonly=True)
            type_, data = conn.search(None, "ALL")
        except BaseException as e:
            print "[-] Search folder {0} failed: {1}".format(folder_name, e)
            continue
        
        # Get email number of this folder
        try:
            msg_id_list = [int(i) for i in data[0].split()]
            msg_num = len(msg_id_list)
            print "[*] {0} emails found in {1} ({2})".format(msg_num, usr, folder_name)
        except BaseException as e:
            print "[-] Can't get email number of {0}: {1}".format(folder_name, e)
            continue
        
        # Get email content and attachments
        for i in msg_id_list:
            print "[*] Downloading email {0}/{1}".format(i, msg_num)
            
            # Get email message
            try:
                type_, data = conn.fetch(i, "(RFC822)")
                msg = email.message_from_string(data[0][1])
            except BaseException as e:
                print "[-] Retrieve email {0} failed: {1}".format(i, e)
                continue
            
            # If message already exist, skip this message
            try:
                msg_md5 = md5(data[0][1]).hexdigest()
                if msg_md5 in download_hash:
                    print "[-] This email has been downloaded in other folder"
                    continue
                else:
                    download_hash.append(msg_md5)
                    download_num += 1
            except BaseException as e:
                print "[-] Parse message md5 failed: {0}".format(e)
                continue
            
            # Parse and save email content/attachments
            try:
                parse_email(msg, download_num)
            except BaseException as e:
                print "[-] Parse email {0} failed: {1}".format(i, e)
    
    # Logout this account
    conn.logout()
        
def parse_email(msg, i):
    """Parse email message and save content & attachments to file
    
    :param msg: mail message
    :param i: ordinal number
    """
    global result_file
    
    # Parse and save email content and attachments
    for part in msg.walk():
        if not part.is_multipart():
            filename = part.get_filename()
            content = part.get_payload(decode=True)
            
            if filename:  # Attachment
                # Decode filename
                h = email.Header.Header(filename)
                dh = email.Header.decode_header(h)
                filename = dh[0][0]
                if dh[0][1]:
                    filename = unicode(filename, dh[0][1])
                    filename = filename.encode("utf-8")
                    print filename

                result_file = os.path.join(result_path, "mail{0}_attach_{1}".format(i, filename))
            else:  # Main content
                result_file = os.path.join(result_path, "mail{0}_text".format(i))
            
            try:
                with open(result_file, "wb") as f:
                    f.write(content)
            except BaseException as e:
                print("[-] Write file of email {0} failed: {1}".format(i, e))


if __name__ == "__main__":
    print("[*] Start download email script")
    start_time = time.time()
    
    mailaddr = MAILADDR
    password = PASSWORD
    server = SERVER
    protocol = PROTOCOL
    use_ssl = USE_SSL
    outdir = OUTDIR
    
    result_path = os.path.join(OUTDIR, mailaddr)
    protocol = parse_protocol(protocol)
    host, port = parse_server(server, use_ssl, protocol)
    
    create_dir(result_path)
    protocol_manager(protocol, host, port, mailaddr, password, use_ssl)
    remove_dir(result_path)
    
    end_time = time.time()
    exec_time = end_time - start_time
    print("[*] Finish download email of {0} in {1:.2f}s".format(mailaddr, exec_time))
