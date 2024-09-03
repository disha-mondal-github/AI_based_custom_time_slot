from pymongo import MongoClient
from datetime import datetime

# Connect to MongoDB
client = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

# Access the database and collections
db = client["DeliverySystem"]  # Replace with your actual database name
recipients_collection = db["recipient"]
postman_collection = db["postmen"]

# Function to fetch the post office of a specific postman
def get_post_office(postman_id):
    postman = postman_collection.find_one({"postman_id": postman_id})
    if postman:
        return postman.get("post_office")
    else:
        print(f"Postman with ID {postman_id} not found.")
        return None

# Function to fetch deliveries for a specific post office on a given date
def fetch_deliveries(postman_id, delivery_date):
    post_office = get_post_office(postman_id)
    
    if not post_office:
        return
    
    # Convert delivery_date to the correct format (assuming 'YYYY-MM-DD' format in the database)
    formatted_date = datetime.strptime(delivery_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    
    # Query the recipients collection for matching deliveries in the post office area
    deliveries = recipients_collection.find({
        "Receiver Post Office": post_office,
        "Date of Delivery": formatted_date
    })

    # Print all deliveries for the post office on the given date
    delivery_list = list(deliveries)
    if delivery_list:
        print(f"Deliveries in Post Office {post_office} on {delivery_date}:")
        for delivery in delivery_list:
            print(delivery)
    else:
        print(f"No deliveries found in Post Office {post_office} on {delivery_date}.")

# Example usage
postman_id = "ZLT7WU"  # Replace with the actual Postman ID
delivery_date = "2024-10-12"  # Replace with the desired date

fetch_deliveries(postman_id, delivery_date)
