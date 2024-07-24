import requests
import time
import csv
import json
from urllib.parse import quote
import os.path
import urllib3
import threading
from datetime import datetime

# Disable SSL warnings
urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)

# Public variable to store informtion
current_searches = []
query_output = []


# Perform the search and get the search_id for further searching
def api_searching (query, ip, headers, company, counter):
    # Try to perform the query and get the search ID to get the result later
    print ("[+] Sending query " + str(counter) +" to " + company)
    encoded_query = quote(query)
    request_url = "https://" + ip + "/api/ariel/searches?query_expression=" + encoded_query
    try:
        # Write Log
        log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " INFO: Sending query " + str(counter) + " to " +company + "\n")
        # Post to the query to the server (verify = False to disable SSL verification)
        r = requests.post(request_url, headers=headers, verify=False)
        api_response = r.json()
        search_id = api_response["search_id"]
        return "success",search_id
    # If the query was incorrect or there is an issue, Print the error message and escape the program
    except Exception as error:
        if type(error).__name__ == "ConnectTimeout":
            return "failed", "Timeout"
        elif "unauthorized" in api_response['http_response']['message'].lower():
            return "failed","Unauthorized"
        elif "semantic errors" in api_response['http_response']['message'].lower():
            return "failed","Semantic Errors"
        else:
            return "failed", error



# Query for result in QRadar
def get_result (company, query_name, ip, search_id, headers):
    # Print message
    print("[+] Retrieving result for " + query_name)
    # Use search ID to retrieve results
    search_query = "https://" + ip + "/api/ariel/searches/" + search_id
    # Continue sending get requests to the server every 30s to see if the search is finished
    while True:
        # Check connection, if failed escape the loop
        try:
            get_search_result = requests.get(search_query, headers=headers, verify=False)
        except:
            print("[-] Failed to connect to " + company + "! Please check your connection and try again!")
            # Write Log
            log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " ERROR: Failed to connect to " +company + "\n")
            break
        search_result = get_search_result.json()
        # Check if the search complete or not
        try:
            if search_result["status"] == 'COMPLETED':
                # Get result
                result_url = search_query + '/results'
                get_events = requests.get(result_url, headers=headers, verify=False)
                # If there is no event within the response, print out the message
                if  len(get_events.json()['events']) == 0:
                    print("[-] No result for " + query_name)
                    delete = requests.delete(search_query, headers=headers, verify=False)

                    #Write to log
                    log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " INFO: " + company + "_" + query_name + " - No Result\n")
                    break
                # Else, return the result
                else:
                    result = get_events.json()["events"]
                    filename = query_name + ".json"
                    print("[+] " + query_name + " completed! Saving output to " + filename)
                    create_output_file (filename, result)
                    #Clean up the search in QRadar
                    delete = requests.delete(search_query, headers=headers, verify=False)

                    # Write to Log
                    log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " INFO: " + company + "_" + query_name + " - Result saved\n")
                    print("[+] Delete saved searches for " + query_name + " from " + company +" QRadar")
                break
                # Wait 30s and try again
            else:
                print("[+] Query incompleted, Please wait 1 more minute...")
                time.sleep(60)
        # Return the error if the search does not exist or other issue 
        except Exception as error:  
            if "The search does not exist".lower() in search_result["description"].lower():  
                print ("[-] The search " + search_id + " does not exist! Please delete the cache file and try again!")
                break
            else:
                print (error)
                break


# Get queries from a file
def get_query (query_file):
    queries =[]
    with open (query_file,"r") as query:
        for line in query:
            queries.append(line)
    return queries




# Save query to a csv file
def create_query_file (filename, data):
    with open (filename, "w", newline='') as output_file:
        fields = ["Company", "Search Name","IP", "Query ID"]
        csvwriter = csv.writer(output_file)
        csvwriter.writerow(fields)
        csvwriter.writerows(data)
            

# Save output to json file
def create_output_file (filename, data):
    if data:
        with open (filename, "w") as output_file:
            json.dump(data,output_file, sort_keys = True, indent = 4, ensure_ascii = False)
    else:
        print ("[-] No data for the query")

#Perform the search on the API and append result to a list for keeping track of the search
def cache_writer (queries, ip, headers, company):
    counter = 1
    for query in queries:
        # Create a dictionary to store information
        query_dict = {}
        # Make request and retrieve the id to use
        status, result = api_searching(query, ip, headers, company, counter)
        
        # If the request is successful
        if status == "success":
            search_name = company + "_Query" + str(counter)
            query_dict["Company"] = company
            query_dict["Search Name"] = search_name
            query_dict["IP"] = ip
            query_dict["Query ID"] = result
            query_output.append(query_dict)
            current_searches.append([company, search_name,ip, result])
            counter += 1
        # Error Handling
        else:
            if result == "Unauthorized":
                print ("[-] The Token provided for " + company + " is incorrect! Please check again!")
                # Write Log
                log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " ERROR: Invalid token for " + company + "\n")
                break
            elif result == "Semantic Errors":
                print ("[-] There is something wrong with " + company + " Query " + str(counter) + "! Please check the query syntax and try again!")
                # Write Log
                log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " ERROR: There is an error for the query syntax of " + query + "\n")
                counter += 1
            elif result == "Timeout":
                print ("[-] Failed to send query to " + company + " QRadar! Please check your connection and try again!")
                # Write Log
                log_file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " ERROR: Connection timeout for " + company + "\n")
                break
            else:
                print (result)
                break

    
    

def threading_search (client_list, query_file):
    # Loops the input file for client information
    headers = {}
    for info in client_list:
        # Extract infromation from input list
        headers["SEC"] = info["Token"]
        ip = info["IP"]
        company = info["Company"]
        queries = get_query(query_file)
        # Running the cache_writer function in threads
        thread = threading.Thread(target = cache_writer, args = (queries, ip, headers, company))
        thread.start()
        thread.join()
        


# Function to create cache file to save temporary information
def create_cache_file (query_file):
    with open("./credentials.csv") as client_info:
        client_reader = list(csv.DictReader(client_info, delimiter=','))
    # Call the function that send queries to client QRadar
    threading_search (client_reader, query_file)

    # If result is empty print error message
    if current_searches == []:
        print ("[-] All Queries failed! Please try again!")
    #  If the result exist add the query to output cache file
    else:
        create_query_file("output_cache.csv",current_searches)
        print ("The query process is finished! Saving cache information to " + os.path.realpath("output_cache.csv"))
    return query_output

# Function for retrieving result using threads
def threading_query (threads_list):
    for item in threads_list:
        headers = {}
        headers["SEC"] = item["Token"]
        thread = threading.Thread(target=get_result, args = (item["Company"], item["Search Name"], item["IP"], item["Query ID"],headers))
        thread.start()
        thread.join()


# Function to go through query information list and retrieve information using credential from credential_list
def query_result (query_list, credential_list):
    for query_item in query_list:
        for client_item in credential_list:
            if query_item["Company"] == client_item["Company"]:
                query_item["Token"] = client_item["Token"]
    # Retrieve results from QRadar using threading
    threading_query(query_list)
 



# Open Log file to write
starttime = datetime.now().strftime("%d%m%Y-%H%M%S")
log_filename = starttime + "-logs.txt"
log_file = open(str(log_filename) ,"a")
log_file.write (datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " INFO: Application Started!\n")


# If the file exist already, extract data from the file
if os.path.isfile("./output_cache.csv"):
    with open ("output_cache.csv") as query_information:
        query_reader = list(csv.DictReader(query_information, delimiter=','))
    with open("./credentials.csv") as client_info:
        client_reader = list(csv.DictReader(client_info, delimiter=','))
    query_result (query_reader, client_reader)
    print("[+] All query completed! Deleting cache file!")
    os.remove("./output_cache.csv")
    

# If not, Call the function to create cache file
else:
    current_searches = create_cache_file ("query.txt")
    with open("./credentials.csv") as client_info:
        client_reader = list(csv.DictReader(client_info, delimiter=','))
    # Pass the output to the function that create result files
    query_result (current_searches, client_reader)
    print("[+] All query completed! Deleting cache file!")
    os.remove("./output_cache.csv")

log_file.close()
