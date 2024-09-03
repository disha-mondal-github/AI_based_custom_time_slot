from pymongo import MongoClient
from datetime import datetime
from llama_index.core import VectorStoreIndex, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings
import openrouteservice
import folium
from geopy.geocoders import Nominatim

# Connect to MongoDB
client = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["DeliverySystem"]
recipients_collection = db["recipient"]
postman_collection = db["postmen"]

# Set up LlamaIndex and Ollama
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
Settings.llm = Ollama(model="llama3", request_timeout=360.0)

# Dictionary to store known post office coordinates
post_office_coordinates = {
    "Andrews Ganj": [28.5624, 77.2381]  # Example coordinates for Andrews Ganj Post Office
    # Add more known post office coordinates here if needed
}

def get_post_office(postman_id):
    postman = postman_collection.find_one({"postman_id": postman_id})
    if postman:
        return postman.get("post_office")
    else:
        print(f"Postman with ID {postman_id} not found.")
        return None

def fetch_deliveries(postman_id, delivery_date):
    post_office = get_post_office(postman_id)
    if not post_office:
        return []
    
    formatted_date = datetime.strptime(delivery_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    
    deliveries = recipients_collection.find({
        "Receiver Post Office": post_office,
        "Date of Delivery": formatted_date
    })
    
    delivery_list = list(deliveries)
    return delivery_list

def prepare_data_for_rag(deliveries):
    documents = []
    for delivery in deliveries:
        doc = Document(
            text=f"Booking ID: {delivery['Booking ID']}, Time Slot: {delivery['Time Slot of Delivery']}, "
                 f"Equipment: {delivery['Equipment Getting Delivered']}, "
                 f"Address: {delivery['Receiver Address']}",
            metadata={
                "doc_id": str(delivery["_id"]),
                "booking_id": delivery['Booking ID'],
                "time_slot": delivery['Time Slot of Delivery']
            }
        )
        documents.append(doc)
    return documents

def parse_time_slot(time_slot):
    start_time, end_time = time_slot.split(" - ")
    start = datetime.strptime(start_time, "%I:%M %p")
    end = datetime.strptime(end_time, "%I:%M %p")
    return start, end

def sort_deliveries_by_time_slot(deliveries):
    def sort_key(delivery):
        start, end = parse_time_slot(delivery['Time Slot of Delivery'])
        duration = (end - start).total_seconds() / 60  # duration in minutes
        return (start, -duration)  # Sort by start time, then by longer duration first

    return sorted(deliveries, key=sort_key)

def resolve_overlaps(sorted_deliveries):
    resolved = []
    for delivery in sorted_deliveries:
        start, end = parse_time_slot(delivery['Time Slot of Delivery'])
        duration = end - start
        if resolved:
            prev_start, prev_end = parse_time_slot(resolved[-1]['Time Slot of Delivery'])
            if start < prev_end:
                # Overlap detected, adjust the current delivery's start time
                new_start = max(start, prev_end)
                new_end = new_start + duration
                delivery['Time Slot of Delivery'] = f"{new_start.strftime('%I:%M %p')} - {new_end.strftime('%I:%M %p')}"
        resolved.append(delivery)
    return resolved

def get_optimal_order_rag(deliveries):
    documents = prepare_data_for_rag(deliveries)
    
    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine()
    
    query = "Analyze the delivery information and provide insights on the optimal route, considering time slots, equipment types, and addresses. Do not reorder the deliveries yourself."
    response = query_engine.query(query)
    
    print("RAG Analysis:", response)
    
    # Sort deliveries based on time slots and resolve overlaps
    sorted_deliveries = sort_deliveries_by_time_slot(deliveries)
    resolved_deliveries = resolve_overlaps(sorted_deliveries)
    
    optimal_order = [
        f"{delivery['Booking ID']} ({delivery['Time Slot of Delivery']}): "
        f"{delivery['Equipment Getting Delivered']} to {delivery['Receiver Address']}"
        for delivery in resolved_deliveries
    ]
    
    return optimal_order

def get_coordinates(address):
    geolocator = Nominatim(user_agent="my_agent")
    location = geolocator.geocode(address)
    if location:
        return [location.latitude, location.longitude]
    else:
        print(f"Could not geocode address: {address}")
        return None

def get_post_office_coordinates(post_office, zipcode):
    if post_office in post_office_coordinates:
        return post_office_coordinates[post_office]
    
    address = f"{post_office} Post Office, Delhi - {zipcode}, India"
    coords = get_coordinates(address)
    
    if coords:
        post_office_coordinates[post_office] = coords  # Store new post office coordinates dynamically
    else:
        print(f"Could not geocode address: {address}")
    
    return coords

def optimize_route(deliveries, post_office, zipcode, api_key):
    client = openrouteservice.Client(key=api_key)
    
    # Start with the post office location
    post_office_coords = get_post_office_coordinates(post_office, zipcode)
    if not post_office_coords:
        print(f"Could not locate the post office: {post_office}, {zipcode}")
        return None
    
    coordinates = [post_office_coords]
    
    for delivery in deliveries:
        coords = get_coordinates(delivery['Receiver Address'])
        if coords:
            coordinates.append(coords)
    
    # Add post office as the end point
    coordinates.append(post_office_coords)
    
    # Request route
    route = client.directions(coordinates=coordinates, profile='driving-car', optimize_waypoints=True)
    
    return route

def create_map(route, deliveries, post_office, zipcode):
    # Create map
    m = folium.Map(location=[28.6139, 77.2090], zoom_start=12)  # Centering map to New Delhi
    
    # Add marker for post office
    post_office_coords = get_post_office_coordinates(post_office, zipcode)
    if post_office_coords:
        folium.Marker(
            post_office_coords,
            popup=f"Post Office: {post_office}",
            icon=folium.Icon(color='green', icon='envelope')
        ).add_to(m)
    
    # Add markers for each delivery point
    for i, delivery in enumerate(deliveries):
        coords = get_coordinates(delivery['Receiver Address'])
        if coords:
            folium.Marker(
                coords,
                popup=f"Delivery {i+1}: {delivery['Booking ID']}",
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
    
    # Add the route to the map
    folium.PolyLine(
        locations=[list(reversed(coord)) for coord in route['routes'][0]['geometry']['coordinates']],
        color="blue",
        weight=2,
        opacity=0.8
    ).add_to(m)
    
    return m

def main(postman_id, delivery_date, api_key):
    deliveries = fetch_deliveries(postman_id, delivery_date)
    if deliveries:
        optimal_order = get_optimal_order_rag(deliveries)
        
        # Get post office details from the first delivery
        post_office = deliveries[0]['Receiver Post Office']
        zipcode = deliveries[0]['Zipcode']
        
        route = optimize_route(deliveries, post_office, zipcode, api_key)
        if route:
            map = create_map(route, deliveries, post_office, zipcode)
            
            # Save the map
            map.save("optimal_route_map.html")
            print("Map saved as 'optimal_route_map.html'")
        else:
            print("Failed to generate route.")
    else:
        print("No deliveries to process.")

# Example usage
postman_id = "ZLT7WU"
delivery_date = "2024-10-12"
api_key = "5b3ce3597851110001cf6248739385263608449e8d4294dc128571f8"

main(postman_id, delivery_date, api_key)
