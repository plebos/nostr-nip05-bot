import json
import ssl
import time
from nostr.filter import Filter, Filters
from nostr.event import Event, EventKind
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.key import PrivateKey
import logging
import traceback
import subprocess
import sqlite3


#TODO: read from config file instead!

bot_log_file_path = 'nip05bot.log'
lnrpc_binary_path = '/path/to/lnsocket/lnrpc' # TODO: python bindings
nip05_domain_name = ""
bot_pubkey = ""
# avoid interaction with that bot :)
gptchatbot_pubkey = "5c10ed0678805156d39ef1ef6d46110fe1e7e590ae04986ccf48ba1299cb53e2" 
bot_privkey_nsec = "nsec..."
db_file_path = "nip05.db"
node_id = ""
node_ip = "1.1.1.1"
node_port = 9735
node_rune = ""


logging.basicConfig(filename=bot_log_file_path, filemode='w', level=logging.DEBUG)
bot_tag_filters = Filters([Filter(tags={"#p":[bot_pubkey]})])
pubkey_metadata_filters = lambda pubkey : Filters([Filter(kinds=[0], authors=[pubkey])])

#TODO: generate random strings
subscription_id_tag = "1283123asda12123123123"
subscription_id_meta = "12312123123aaadddd"

build_request = lambda subscription_id,filters: [*[ClientMessageType.REQUEST, subscription_id], *filters.to_json_array()]
request_tag = build_request(subscription_id_tag, bot_tag_filters)

def get_invoice(node_id,node_addr, rune, amount_msat, label, description):
    # Call the binary with the arguments

    invoice_params = json.dumps({'amount_msat':amount_msat, 'label':label, 'description':description})
    output = subprocess.run([lnrpc_binary_path, node_id, node_addr, rune, 'invoice', invoice_params], capture_output=True)

    # Print the stdout and stderr
    out = output.stdout
    err = output.stderr

    # Check the return code
    if output.returncode == 0:
        logging.debug('The binary was executed successfully')
        logging.debug(out)   
    else:
        logging.debug('There was an error executing the binary')
        logging.debug(err)   
    
    return json.loads(out)["result"]["bolt11"]


def get_relay_manager(subscription_id, filters, relays=["wss://nostr-pub.wellorder.net","wss://relay.damus.io", "wss://nostr.bitcoiner.social","wss://nostr.onsats.org", "wss://relay.nostr.info"]):
    rm = RelayManager()
    for relay in relays:
        rm.add_relay(relay)
        
    rm.add_subscription(subscription_id, filters)
    rm.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
    return rm

relay_manager = get_relay_manager(subscription_id_tag, bot_tag_filters)

time.sleep(1.25) # allow the connections to open

message = json.dumps(request_tag)
logging.debug(message)
relay_manager.publish_message(message)
time.sleep(1) # allow the messages to send
private_key = PrivateKey.from_nsec(bot_privkey_nsec)


# Connect to the database
conn = sqlite3.connect(db_file_path)

# Create a cursor
cursor = conn.cursor()

# Create the used_ids table if it does not exist, and orders_status
cursor.execute('''CREATE TABLE IF NOT EXISTS used_ids (id TEXT PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS orders_status (label TEXT PRIMARY KEY, name TEXT, pubkey TEXT, event_id TEXT, paid BOOLEAN)''')


# Commit the transaction
conn.commit()

pubkey_name = {}
pubkeys_subscribed = [] 

reconnect_count = 0 

while True:
    try:
        while relay_manager.message_pool.has_events():
            event_msg = relay_manager.message_pool.get_event()
            #logging.debug(event_msg.event)
            if(event_msg.event.public_key == bot_pubkey):
                # ignore our bot notes
                #relay_manager.message_pool.pop_event()
                continue
            if(event_msg.event.public_key == gptchatbot_pubkey):
                continue


            if(event_msg.event.kind == EventKind.SET_METADATA):
                meta = json.loads(event_msg.event.content)
                logging.debug("{} name is {}".format(event_msg.event.public_key, meta["name"]))
                pubkey_name[event_msg.event.public_key] = meta["name"]
                #relay_manager.message_pool.pop_event()
                continue
            
            if(event_msg.event.kind != EventKind.TEXT_NOTE):
                logging.debug("Ignoring non text-note event kind")
                continue

            logging.debug("INCOMING EVENT:\n")
            logging.debug({'id': str(event_msg.event.id), 'content': str(event_msg.event.content), 'pubkey': str(event_msg.event.public_key), 'tags': str(event_msg.event.tags)})
            # Execute the SELECT statement to retrieve the ID from the table
            
            cursor.execute("SELECT id FROM used_ids WHERE id=?", ((event_msg.event.id,)))
            # Fetch the result of the query
            #result = 2    
            result = cursor.fetchone()
            # Check if the ID exists in the table

            if result is not None:
                logging.debug("ID {} has been replied already".format(event_msg.event.id))
            else:
                if event_msg.event.public_key not in pubkeys_subscribed:
                    logging.debug("Adding pubkey subscription")
                    relay_manager.add_subscription(subscription_id_meta, pubkey_metadata_filters(event_msg.event.public_key))
                    pubkeys_subscribed.append(event_msg.event.public_key)
                    logging.debug("Publishing request")
                    request_meta = build_request(subscription_id_meta, pubkey_metadata_filters(event_msg.event.public_key))
                    message = json.dumps(request_meta)
                    relay_manager.publish_message(message)
                    logging.debug(message)
                else:
                    logging.debug("Waiting for {} name to be retrieved".format(event_msg.event.public_key))

                if event_msg.event.public_key in pubkey_name:
                    # Define a list of IDs to insert
                    name = pubkey_name[event_msg.event.public_key]

                    # Execute the SELECT statement to retrieve the row from the table
                    cursor.execute('''SELECT * FROM orders_status WHERE name=? AND paid=1''', (name,))

                    # Fetch the result of the query
                    result = cursor.fetchone()
                    

                    if result is None:
                        ''' 
                        there is no paid invoice with that name
                        '''

                        import random
                        import string
                    
                        temp_add_to_tag = ''.join(random.choices(string.ascii_lowercase, k=5))

                        namelen_to_sats = {1: 70000, 2:45000, 3:25000, 4:20000, 5:20000}

                        invoice_label = event_msg.event.id + temp_add_to_tag
                        invoice_amount_msats = namelen_to_sats.get(len(name), 10000) * 1000

                        bolt11 = get_invoice(node_id, f"{node_ip}:{node_port}", node_rune, invoice_amount_msats, invoice_label, "{}@{} NIP-05 registration".format(name, nip05_domain_name))

                        response = Event(public_key=private_key.public_key.hex(), content="Hi #[1]\nPay that invoice to register {}@{} NIP-05⚡️ {}".format(name, nip05_domain_name, bolt11), tags=[['e', event_msg.event.id], ['p',event_msg.event.public_key]])
                        response.sign(private_key.hex())
                    
                        message = json.dumps([ClientMessageType.EVENT, response.to_json_object()])
                        #logging.debug("Published response: {}".format(message))
                        #cursor.execute('''INSERT INTO used_ids (id) VALUES (?)''', (event_msg.event.id,))
                        cursor.execute('''INSERT INTO orders_status (label, name, pubkey, event_id, paid) VALUES (?, ?, ?, ?, ?)''', (invoice_label,name,event_msg.event.public_key,event_msg.event.id, 0))
                    
                        #logging.debug("ID {} has been added to db".format(event_msg.event.id))
                    # Commit the transaction
                        conn.commit()
                    else:
                        response = Event(public_key=private_key.public_key.hex(), content="Hi #[1]\n that nip-05 has been purchased already, please choose another one⚡".format(name), tags=[['e', event_msg.event.id], ['p',event_msg.event.public_key]])
                        response.sign(private_key.hex())

                        message = json.dumps([ClientMessageType.EVENT, response.to_json_object()])
                    
                    #relay_manager.message_pool.add_event(event_msg)
                    logging.debug("Should publish that {}".format(message))
                    try:
                        relay_manager.publish_message(message)
                        logging.debug("Adding {} to used_ids".format(event_msg.event.id))
                        cursor.execute('''INSERT INTO used_ids (id) VALUES (?)''', (event_msg.event.id,))
                        conn.commit()
                    except Exception as e:
                        logging.error(e)
                        logging.error(traceback.format_exc())
                        relay_manager.close_connections()
                        relay_manager = get_relay_manager(subscription_id_tag, bot_tag_filters)

                    #logging.debug("Adding {} to used_ids".format(event_msg.event.id))
                    #cursor.execute('''INSERT INTO used_ids (id) VALUES (?)''', (event_msg.event.id,))
                    #conn.commit()
                    continue
                
                # That event haven't been handled yet, return to queue
                relay_manager.message_pool.add_event(event_msg)

            time.sleep(5)
            #if(reconnect_count%1000 == 0):
            #    relay_manager.close_connections()
            #    relay_manager = get_relay_manager(subscription_id_tag, bot_tag_filters)
            #    reconnect_count += 1

    except Exception as e:
        logging.error(e)
        logging.error(traceback.format_exc())
        # Connect to the database
        conn = sqlite3.connect(db_file_path)
        time.sleep(3)

relay_manager.close_connections()
conn.close()
