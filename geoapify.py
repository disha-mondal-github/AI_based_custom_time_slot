import requests
from pymongo import MongoClient
from datetime import datetime

# Connect to MongoDB
client = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

# Access the database and collections
db = client["DeliverySystem"]  # Replace with your actual database name
recipients_collection = db["recipient"]
postman_collection = db["postmen"]

GEOAPIFY_API_KEY = "2c66eb88f80b40299cf87f96c7f8228c"

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

    delivery_list = list(deliveries)
    if delivery_list:
        print(f"Deliveries in Post Office {post_office} on {delivery_date}:")
        addresses = []
        for delivery in delivery_list:
            print(delivery)
            addresses.append(delivery["Receiver Address"])
        return addresses
    else:
        print(f"No deliveries found in Post Office {post_office} on {delivery_date}.")
        return []

# Function to get latitude and longitude from an address using Geocoding API
def geocode_address(address):
    api_url = f"https://api.geoapify.com/v1/geocode/search?text={address}&apiKey={GEOAPIFY_API_KEY}"
    response = requests.get(api_url)
    data = response.json()
    if data['features']:
        return data['features'][0]['geometry']['coordinates']
    else:
        print(f"Address not found: {address}")
        return None

# Function to get optimal route using Routing API
def get_optimal_route(waypoints):
    waypoints_str = '|'.join([f"{lat},{lon}" for lat, lon in waypoints])
    api_url = f"https://api.geoapify.com/v1/routing?waypoints={waypoints_str}&mode=drive&apiKey={GEOAPIFY_API_KEY}"
    response = requests.get(api_url)
    route = response.json()
    return route

# Main function to fetch deliveries and calculate the route
def main(postman_id, delivery_date):
    addresses = fetch_deliveries(postman_id, delivery_date)
    
    if addresses:
        # Convert addresses to coordinates
        waypoints = []
        for address in addresses:
            coordinates = geocode_address(address)
            if coordinates:
                waypoints.append(coordinates)
        
        if waypoints:
            # Get the optimal route
            route = get_optimal_route(waypoints)
            print(f"Optimal Route: {route}")
        else:
            print("No valid waypoints for routing.")
    else:
        print("No deliveries to process.")

# Example usage
postman_id = "ZLT7WU"  # Replace with the actual Postman ID
delivery_date = "2024-10-12"  # Replace with the desired date

main(postman_id, delivery_date)
