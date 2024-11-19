import streamlit as st
from pymongo import MongoClient
from datetime import datetime
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.mistralai import MistralAI
from llama_index.core import StorageContext, load_index_from_storage
from dotenv import load_dotenv
import time
import os
import pickle
from pathlib import Path
import requests
import folium
from folium import plugins
from streamlit_folium import st_folium
import polyline
from typing import Tuple, List, Optional
import math

# Initialize session state variables
if 'show_map' not in st.session_state:
    st.session_state.show_map = False
if 'current_deliveries' not in st.session_state:
    st.session_state.current_deliveries = None
if 'current_postman' not in st.session_state:
    st.session_state.current_postman = None

# Load environment variables
load_dotenv()

# Constants
ACCESS_TOKEN = "pk.eyJ1IjoiZGVhZHNob3QxNjExIiwiYSI6ImNtMncwYndmZDAxdGwybXIyODR1NmVzd2MifQ.IEomXlC1NcM6wD6LyAWRWQ"
DELHI_BBOX = '77.1,28.4,77.3,28.7'

# MongoDB connection
client = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["DeliverySystem"]
recipients_collection = db["recipient"]
postman_collection = db["postmen"]

# Initialize models with caching
@st.cache_resource
def init_models():
    embedding_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
    llm = MistralAI(api_key=os.getenv("MISTRAL_API_KEY"))
    Settings.embed_model = embedding_model
    Settings.llm = llm
    return embedding_model, llm

# Cache directory setup
INDEX_CACHE_DIR = Path("./cache")
INDEX_CACHE_DIR.mkdir(exist_ok=True)

# Existing functions from first code
# [Previous functions from first code: get_cache_key, get_cached_index, save_index_to_cache, 
# get_postman_details, fetch_deliveries, prepare_data_for_rag, parse_time_slot, 
# get_sorted_deliveries, resolve_overlaps, update_delivery_status, get_optimal_order_rag]

def get_cache_key(deliveries):
    return "_".join(str(d['Booking ID']) for d in deliveries)

def get_cached_index(cache_key):
    cache_file = INDEX_CACHE_DIR / f"{cache_key}.pickle"
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except:
            return None
    return None

def save_index_to_cache(cache_key, index):
    cache_file = INDEX_CACHE_DIR / f"{cache_key}.pickle"
    with open(cache_file, 'wb') as f:
        pickle.dump(index, f)

@st.cache_data
def get_postman_details(postman_id):
    postman = postman_collection.find_one({"postman_id": postman_id})
    if postman:
        return {
            "postman_name": postman.get("postman_name"),
            "postman_phn_no": postman.get("postman_phn_no"),
            "post_office": postman.get("post_office")
        }
    return None

def fetch_deliveries(postman_id, delivery_date):
    postman = get_postman_details(postman_id)
    
    if not postman:
        return [], None
    
    post_office = postman['post_office']
    formatted_date = datetime.strptime(delivery_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    
    # Add index on commonly queried fields
    recipients_collection.create_index([
        ("Receiver Post Office", 1),
        ("Date of Delivery", 1)
    ])
    
    deliveries = recipients_collection.find({
        "Receiver Post Office": post_office,
        "Date of Delivery": formatted_date
    })
    
    delivery_list = list(deliveries)
    return delivery_list, postman

def prepare_data_for_rag(deliveries):
    return [Document(
        text=f"ID:{d['Booking ID']} Time:{d['Time Slot of Delivery']} Eq:{d['Equipment Getting Delivered']} Addr:{d['Receiver Address']}",
        metadata={"booking_id": d['Booking ID']}
    ) for d in deliveries]

def parse_time_slot(time_slot):
    start_time, end_time = time_slot.split(" - ")
    start = datetime.strptime(start_time, "%I:%M %p")
    end = datetime.strptime(end_time, "%I:%M %p")
    return start, end

@st.cache_data
def get_sorted_deliveries(_deliveries):
    deliveries_tuple = tuple(
        (d['Booking ID'], d['Time Slot of Delivery'], d['Equipment Getting Delivered'], 
         d['Receiver Address'], d['Receiver Phone No.'], d.get('Delivery Status', 'Not Delivered'), 
         d['_id'], d.get('Receiver Name', 'N/A'))  # Added Receiver Name
        for d in _deliveries
    )
    sorted_tuples = sorted(
        deliveries_tuple,
        key=lambda d: parse_time_slot(d[1])[0]
    )
    return [
        {
            'Booking ID': d[0],
            'Time Slot of Delivery': d[1],
            'Equipment Getting Delivered': d[2],
            'Receiver Address': d[3],
            'Receiver Phone No.': d[4],
            'Delivery Status': d[5],
            '_id': d[6],
            'Receiver Name': d[7]  # Added Receiver Name
        }
        for d in sorted_tuples
    ]

def resolve_overlaps(sorted_deliveries):
    if not sorted_deliveries:
        return []
        
    resolved = [sorted_deliveries[0]]
    for delivery in sorted_deliveries[1:]:
        curr_start, curr_end = parse_time_slot(delivery['Time Slot of Delivery'])
        prev_start, prev_end = parse_time_slot(resolved[-1]['Time Slot of Delivery'])
        
        if curr_start < prev_end:
            new_start = prev_end
            duration = curr_end - curr_start
            new_end = new_start + duration
            delivery['Time Slot of Delivery'] = f"{new_start.strftime('%I:%M %p')} - {new_end.strftime('%I:%M %p')}"
        
        resolved.append(delivery)
    return resolved

def update_delivery_status(delivery_id, status):
    try:
        result = recipients_collection.update_one(
            {"_id": delivery_id},
            {"$set": {"Delivery Status": status}}
        )
        return result.modified_count > 0
    except Exception as e:
        st.error(f"Error updating delivery status: {str(e)}")
        return False

def get_optimal_order_rag(deliveries):
    if not deliveries:
        return []
    
    cache_key = get_cache_key(deliveries)
    index = get_cached_index(cache_key)
    
    if not index:
        documents = prepare_data_for_rag(deliveries)
        index = VectorStoreIndex.from_documents(documents)
        save_index_to_cache(cache_key, index)
    
    query_engine = index.as_query_engine(
        similarity_top_k=3,
        response_mode="compact"
    )
    
    response = query_engine.query(
        "What's the optimal delivery route? Consider time slots and addresses."
    )
    
    sorted_deliveries = get_sorted_deliveries(deliveries)
    resolved_deliveries = resolve_overlaps(sorted_deliveries)
    
    return resolved_deliveries

# Map-related functions from second code
def create_numbered_marker(number: int, color: str = 'blue') -> folium.DivIcon:
    """Create a circular marker with a number inside."""
    return folium.DivIcon(
        html=f'''
            <div style="
                background-color: {color};
                color: white;
                border-radius: 50%;
                width: 25px;
                height: 25px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 14px;
                border: 2px solid white;
                box-shadow: 0 0 4px rgba(0,0,0,0.4);
            ">
                {number}
            </div>
        '''
    )

@st.cache_data(ttl=3600)  # Cache results for 1 hour
def geocode_address(address: str, original_address: str) -> Tuple[Optional[List[float]], Optional[str]]:
    """Geocoding function with consistent fallback behavior for invalid addresses."""
    
    # First check if we have cached coordinates for this exact address
    cache_key = f"geocode_{address}"
    if cache_key in st.session_state:
        return st.session_state[cache_key], original_address

    url = "https://api.mapbox.com/geocoding/v5/mapbox.places/"
    base_params = {
        'access_token': ACCESS_TOKEN,
        'limit': 1,
        'country': 'IN',
        'bbox': DELHI_BBOX,
        'types': 'address,poi,place',
        'proximity': '77.2,28.5'
    }
    
    def try_geocoding(query: str, params: dict) -> Optional[List[float]]:
        try:
            response = requests.get(f"{url}{query}.json", params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'features' in data and data['features']:
                return data['features'][0]['geometry']['coordinates']
        except requests.exceptions.RequestException:
            pass
        return None

    # Try different geocoding strategies in a consistent order
    strategies = [
        # Strategy 1: Full address
        (address, base_params),
        
        # Strategy 2: First part of address with post office area
        (f"{address.split(',')[0]}, New Delhi", base_params),
        
        # Strategy 3: Extracted area name with stricter parameters
        (f"{address.split(',')[0]}", {**base_params, 'types': 'place,neighborhood'}),
        
        # Strategy 4: Deterministic fallback point for the specific post office area
        (f"Central Delhi", {**base_params, 'types': 'place'})
    ]

    for query, params in strategies:
        coords = try_geocoding(query, params)
        if coords:
            # Add small deterministic offset based on hash of original address
            # This ensures same invalid address always gets same offset
            offset = (
                (hash(original_address) % 100) / 10000,  # Lat offset (-0.01 to 0.01)
                (hash(original_address) % 50) / 10000    # Lon offset (-0.005 to 0.005)
            )
            final_coords = [
                coords[0] + offset[1],  # Add lon offset
                coords[1] + offset[0]   # Add lat offset
            ]
            
            # Cache the result
            st.session_state[cache_key] = final_coords
            return final_coords, original_address

    # Final fallback: Central Delhi with deterministic offset
    fallback_coords = [77.2090, 28.6139]  # Central Delhi coordinates
    offset = (
        (hash(original_address) % 100) / 10000,
        (hash(original_address) % 50) / 10000
    )
    final_fallback = [
        fallback_coords[0] + offset[1],
        fallback_coords[1] + offset[0]
    ]
    
    # Cache the fallback result
    st.session_state[cache_key] = final_fallback
    st.warning(f"Using approximate location for address: {original_address}")
    return final_fallback, original_address

def adjust_nearby_coordinates(coordinates: List[List[float]], min_distance: float = 0.0001) -> List[List[float]]:
    """Adjust coordinates that are too close to each other."""
    adjusted = coordinates.copy()
    
    for i in range(len(adjusted)):
        for j in range(i + 1, len(adjusted)):
            if adjusted[i] and adjusted[j]:
                dx = adjusted[i][0] - adjusted[j][0]
                dy = adjusted[i][1] - adjusted[j][1]
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance < min_distance:
                    angle = (j * 2 * math.pi) / len(coordinates)
                    adjusted[j][0] += min_distance * math.cos(angle)
                    adjusted[j][1] += min_distance * math.sin(angle)
    
    return adjusted

@st.cache_data
def get_optimized_route(coordinates: List[List[float]], leg_index: int = None) -> Optional[dict]:
    """Get optimized route between coordinates using Mapbox Directions API."""
    if leg_index is not None:
        coords = coordinates[leg_index:leg_index + 2]
    else:
        coords = coordinates
        
    coordinates_string = ";".join([f"{lon},{lat}" for lon, lat in coords])
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coordinates_string}"
    
    params = {
        'access_token': ACCESS_TOKEN,
        'overview': 'full',
        'geometries': 'polyline',
        'steps': 'true',
        'annotations': 'distance,duration'
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting route: {str(e)}")
        return None

def display_delivery_schedule(deliveries):
    """Display delivery schedule with status updates."""
    for i, delivery in enumerate(deliveries, 1):
        st.write(f"**Stop {i}**")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"""
            * **Booking ID:** {delivery['Booking ID']}
            * **Receiver Name:** {delivery['Receiver Name']}
            * **Phone Number:** {delivery['Receiver Phone No.']}
            * **Address:** {delivery['Receiver Address']}
            * **Time Slot:** {delivery['Time Slot of Delivery']}
            * **Equipment:** {delivery['Equipment Getting Delivered']}
            """)
            
        with col2:
            current_status = delivery.get('Delivery Status', 'Not Delivered')
            
            if current_status != 'Delivered':
                key = f"checkbox_{delivery['Booking ID']}"
                if st.checkbox('Mark as Delivered', key=key, help="Click to confirm delivery"):
                    if update_delivery_status(delivery['_id'], 'Delivered'):
                        st.success(f"Delivery {delivery['Booking ID']} marked as delivered!")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.experimental_rerun()
                    else:
                        st.error("Failed to update delivery status")
            else:
                st.write("✅ Delivered")
        
        st.markdown("---")

def display_route_map(post_office: str, deliveries: list):
    """Display the route map with all delivery stops."""
    route_colors = ['#FF3333', '#33FF33', '#3333FF', '#FF33FF', '#FFFF33', '#33FFFF', '#FF9933']
    
    with st.spinner('Generating map...'):
        post_office_coords, _ = geocode_address(post_office, post_office)
        
        if post_office_coords:
            delivery_coords = []
            delivery_addresses = []
            invalid_addresses = []
            
            for idx, delivery in enumerate(deliveries, 1):
                coords, matched_address = geocode_address(
                    delivery['Receiver Address'], 
                    delivery['Receiver Address']
                )
                if coords:
                    delivery_coords.append(coords)
                    delivery_addresses.append(matched_address)
                    if coords[0] == 77.2090 or coords[1] == 28.6139:  # If using fallback coordinates
                        invalid_addresses.append(f"Stop {idx}: {matched_address}")

            if invalid_addresses:
                st.warning("The following addresses were approximated:\n" + "\n".join(invalid_addresses))

            
            if delivery_coords:
                adjusted_coords = adjust_nearby_coordinates(delivery_coords)
                
                route_map = folium.Map(
                    location=[post_office_coords[1], post_office_coords[0]],
                    zoom_start=14,
                    tiles="cartodbpositron"
                )
                
                # Add post office marker
                folium.Marker(
                    location=[post_office_coords[1], post_office_coords[0]],
                    popup=folium.Popup("Post Office (Start/End)<br>" + post_office, max_width=300),
                    icon=folium.Icon(color='red', icon='home', prefix='fa')
                ).add_to(route_map)
                
                # Add delivery point markers
                for idx, ((lon, lat), address) in enumerate(zip(adjusted_coords, delivery_addresses), 1):
                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(f"Stop {idx}<br>{address}", max_width=300),
                        icon=create_numbered_marker(idx)
                    ).add_to(route_map)
                
                # Create routes
                all_coords = [post_office_coords] + adjusted_coords + [post_office_coords]
                total_duration = 0
                total_distance = 0
                
                for i in range(len(all_coords) - 1):
                    route_data = get_optimized_route(all_coords, i)
                    
                    if route_data and 'routes' in route_data and route_data['routes']:
                        route = route_data['routes'][0]
                        
                        if 'geometry' in route:
                            route_coords = polyline.decode(route['geometry'])
                            color = route_colors[i % len(route_colors)]
                            
                            path_coords = [[lat, lon] for lat, lon in route_coords]
                            
                            plugins.AntPath(
                                locations=path_coords,
                                color=color,
                                weight=3,
                                opacity=0.8,
                                popup=f"Route Segment {i+1}",
                                delay=1000,
                                dash_array=[10, 20],
                                pulse_color='#FFFFFF'
                            ).add_to(route_map)
                            
                            if 'duration' in route:
                                total_duration += route['duration']
                            if 'distance' in route:
                                total_distance += route['distance']
                
                # Display map and route information
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st_folium(route_map, width=800, height=600)
                
                with col2:
                    st.write("### Route Details")
                    st.write(f"**Start:** {post_office} 🏠")
                    for idx, addr in enumerate(delivery_addresses, 1):
                        st.write(f"**Stop {idx}:** {addr}")
                    st.write(f"**End:** {post_office} 🏠")
                    
                    hours = total_duration // 3600
                    minutes = (total_duration % 3600) // 60
                    st.metric("Estimated Duration", f"{int(hours)}h {int(minutes)}m")
                    
                    distance_km = total_distance / 1000
                    st.metric("Total Distance", f"{distance_km:.1f} km")
                    
                    st.write("### Summary")
                    st.metric("Total Stops", len(delivery_coords))
            else:
                st.error("No valid delivery locations found")
        else:
            st.error("Unable to locate post office")

def toggle_map():
    st.session_state.show_map = not st.session_state.show_map

def main():
    st.set_page_config(layout="wide", page_title="Postman Delivery System")
    
    st.title("Postman Delivery System")
    
    # Initialize models at startup
    init_models()
    
    postman_id = st.text_input("Enter Postman ID")
    delivery_date = st.date_input("Enter Delivery Date", min_value=datetime.today())

    if st.button("Get Schedule"):
        with st.spinner("Generating schedule..."):
            delivery_date_str = delivery_date.strftime("%Y-%m-%d")
            deliveries, postman = fetch_deliveries(postman_id, delivery_date_str)
            
            # Store the results in session state
            st.session_state.current_deliveries = deliveries
            st.session_state.current_postman = postman
            st.session_state.show_map = False  # Reset map state when getting new schedule
            
    # Display postman and delivery information if available
    if st.session_state.current_postman:
        st.write("### Postman Details")
        st.write(f"**Name:** {st.session_state.current_postman['postman_name']}")
        st.write(f"**Phone Number:** {st.session_state.current_postman['postman_phn_no']}")
        st.write(f"**Post Office:** {st.session_state.current_postman['post_office']}")
        
        if st.session_state.current_deliveries:
            st.write("### Delivery Schedule")
            sorted_deliveries = get_optimal_order_rag(st.session_state.current_deliveries)
            display_delivery_schedule(sorted_deliveries)
            
            # Use a button with session state to toggle map visibility
            if st.button("Toggle Route Map", on_click=toggle_map):
                pass
            
            # Display map based on session state
            if st.session_state.show_map:
                display_route_map(
                    f"{st.session_state.current_postman['post_office']}, New Delhi, India",
                    sorted_deliveries
                )
        else:
            st.write("No deliveries found for the given date.")
    else:
        if postman_id:  # Only show this message if a postman ID was entered
            st.write("Postman ID not found.")

if __name__ == "__main__":
    main()