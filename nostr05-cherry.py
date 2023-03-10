import json
import sqlite3

import cherrypy

# Create a global variable to store the database connection
db_conn = None
db_file_path = "nip05.db"
bot_name = 'nip05bot'
bot_pubkey = ""


def create_db_connection():
    global db_conn
    db_conn = sqlite3.connect(db_file_path, check_same_thread=False)


def build_nip05_json(name, pubkey):
    val = {"names" : {name : pubkey}}
    return json.loads(json.dumps(val))


class Server:
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def default(self, *args, **kwargs):
        #return '{"error": "hello"}'
        
        if 'name' not in kwargs:
            return json.loads('{"error":"name should be specified"}')
        
        name = kwargs['name']

        if name == bot_name:
            return build_nip05_json(db_file_path, bot_pubkey)

        cursor = db_conn.cursor()
        cursor.execute('''SELECT label, pubkey, paid FROM orders_status WHERE paid=1 AND name=?''', (name,))
        
        # Fetch the result of the query
        result = cursor.fetchone()

        # Check if the order exists in the table and has been paid
        if result is not None:
            label, pubkey, paid = result
            return build_nip05_json(name, pubkey)
        else:
            return json.loads('{"error":"you have to purchase that name first by tagging nip05bot on nostr"}')
        
if __name__ == '__main__':
    create_db_connection()
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 9000})
    cherrypy.quickstart(Server(), '/', {})