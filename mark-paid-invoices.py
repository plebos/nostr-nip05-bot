import json
import os
import sqlite3
import time

db_path = "nip05.db"
lnrpc_binary_path = '/path/to/lnrpc'
node_id = ""
node_ip = ""
node_port = 8935
# This rune should allow listinvoices with some limit
node_rune = "" 


def get_invoices(node_id,node_addr, rune):
    import subprocess

    # Call the binary with the arguments

    invoice_params = json.dumps({})
    output = subprocess.run([lnrpc_binary_path, node_id, node_addr, rune, 'listinvoices',invoice_params], capture_output=True)

    # Print the stdout and stderr
    out = output.stdout
    err = output.stderr

    # Check the return code
    if output.returncode == 0:
        print('The binary was executed successfully')
    else:
        print('There was an error executing the binary')
    #print(out)


    return json.loads(out)["result"]["invoices"]

db_conn = sqlite3.connect(db_path)

while True:
    try:

        invoices = get_invoices(node_id, f"{node_ip}:{node_port}", node_rune)

        labels = [i["label"] for i in invoices if i["status"] == "paid"]
        print(labels)
        # Create a dynamic parameter list for the UPDATE statement
        params = ','.join('?' * len(labels))

        # Execute the UPDATE statement with the dynamic parameter list
        cursor = db_conn.cursor()
        cursor.execute(f'''UPDATE orders_status SET paid=1 WHERE label IN ({params})''', labels)

        # Commit the transaction
        db_conn.commit()

    except Exception as e:
        # Print the exception message if an error occurs
        print(e)

    # Sleep for 10 seconds
    time.sleep(10)



# Close the connection
conn.close()
#print(info)
