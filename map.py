import requests
import folium
from folium import plugins
import streamlit as st
from streamlit_folium import st_folium
import polyline
from typing import Tuple, List, Optional
import math

# Constants
ACCESS_TOKEN = "pk.eyJ1IjoiZGVhZHNob3QxNjExIiwiYSI6ImNtMncwYndmZDAxdGwybXIyODR1NmVzd2MifQ.IEomXlC1NcM6wD6LyAWRWQ"
DELHI_BBOX = '77.1,28.4,77.3,28.7'

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

@st.cache_data
def geocode_address(address: str, original_address: str) -> Tuple[Optional[List[float]], Optional[str]]:
    """
    Geocoding function that returns coordinates for any valid address.
    """
    url = "https://api.mapbox.com/geocoding/v5/mapbox.places/"
    params = {
        'access_token': ACCESS_TOKEN,
        'limit': 1,
        'country': 'IN',
        'bbox': DELHI_BBOX,
        'types': 'address,poi,place',
        'proximity': '77.2,28.5'  # Center of Delhi
    }
    
    # Clean address
    address = address.replace("SAHAPUR", "SHAHPUR").replace("  ", " ")
    
    try:
        response = requests.get(f"{url}{address}.json", params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'features' in data and data['features']:
            coords = data['features'][0]['geometry']['coordinates']
            return coords, original_address
            
    except requests.exceptions.RequestException:
        pass
    
    # If first attempt fails, try with simpler address
    try:
        # Extract main area name
        main_areas = ["SHAHPUR JAT", "KALKAJI", "GAUTAM NAGAR", "SOUTH EXTENSION"]
        area = next((part.strip() for part in address.split(",") 
                    if any(area in part.upper() for area in main_areas)), 
                   address.split(",")[0])
        
        response = requests.get(f"{url}{area}, New Delhi.json", params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'features' in data and data['features']:
            coords = data['features'][0]['geometry']['coordinates']
            return coords, original_address
            
    except (requests.exceptions.RequestException, StopIteration):
        pass
    
    st.error(f"Failed to geocode: {original_address}")
    return None, None

def adjust_nearby_coordinates(coordinates: List[List[float]], min_distance: float = 0.0001) -> List[List[float]]:
    """
    Adjust coordinates that are too close to each other by adding small offsets.
    min_distance is approximately 11 meters at Delhi's latitude.
    """
    adjusted = coordinates.copy()
    
    for i in range(len(adjusted)):
        for j in range(i + 1, len(adjusted)):
            if adjusted[i] and adjusted[j]:  # Check if coordinates exist
                # Calculate distance between points
                dx = adjusted[i][0] - adjusted[j][0]
                dy = adjusted[i][1] - adjusted[j][1]
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance < min_distance:
                    # Add small offset to the second point in different directions
                    angle = (j * 2 * math.pi) / len(coordinates)  # Distribute points in a circle
                    adjusted[j][0] += min_distance * math.cos(angle)
                    adjusted[j][1] += min_distance * math.sin(angle)
    
    return adjusted

@st.cache_data
def get_optimized_route(coordinates: List[List[float]], leg_index: int = None) -> Optional[dict]:
    """
    Get optimized route between coordinates using Mapbox Directions API.
    """
    if leg_index is not None:
        # Get route for specific segment
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
        with st.spinner('Calculating optimal route...'):
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting route: {str(e)}")
        return None

def main():
    st.set_page_config(layout="wide", page_title="Postman Delivery Route Map")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.title("Postman Delivery Route Map")
        map_placeholder = st.empty()
    
    # Post Office and Delivery Addresses
    post_office = "Andrews Ganj Post Office, New Delhi, Delhi 110049, India"
    addresses = [
        "274, Shop no, 03, Masjid Moth Rd, South Extension, part II, South Extension II, New Delhi, Delhi 110049, India",
        "117/1 Gautam nagar,Sudarshan cinema road new Delhi 110049 Area code- Gautam nagar",
        "4 b 1st floor gali no 4 near gumbad gate sahpur jat new delhi, THE KHAND, KALKAJI, South East, Delhi, 110049",
        "129 A, Shahpur Jat, New Delhi - 110049",
        "129A S/F VILL-SHAHPUR JAT , SAHAPUR JAT , HAUZ KHAS, South , Delhi-110049",
        "119 ,SISHAN HOUSE, SHAHPUR JAT NEW DELHI 110049, SAHAPUR JAT , HAUZ KHAS, South , Delhi - 110049"
    ]
    
    # Define a list of colors for route segments
    route_colors = ['#FF3333', '#33FF33', '#3333FF', '#FF33FF', '#FFFF33', '#33FFFF', '#FF9933']
    
    with st.spinner('Initializing...'):
        post_office_coords, post_office_address = geocode_address(post_office, post_office)
        
        if post_office_coords:
            delivery_coords = []
            delivery_addresses = []
            
            with col2:
                st.write("### Delivery Stops")
                progress_bar = st.progress(0)
                
                for idx, address in enumerate(addresses):
                    coords, matched_address = geocode_address(address, address)
                    if coords:
                        delivery_coords.append(coords)
                        delivery_addresses.append(matched_address)
                        st.success(f"✓ Stop {len(delivery_coords)}: {matched_address}")
                    else:
                        st.error(f"❌ Failed to geocode: {address}")
                    progress_bar.progress((idx + 1) / len(addresses))
            
            if delivery_coords:
                # Adjust coordinates to ensure all markers are visible
                adjusted_coords = adjust_nearby_coordinates(delivery_coords)
                
                # Create base map
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
                
                # Add numbered markers for delivery points
                for idx, ((lon, lat), address) in enumerate(zip(adjusted_coords, delivery_addresses), 1):
                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(f"Stop {idx}<br>{address}", max_width=300),
                        icon=create_numbered_marker(idx)
                    ).add_to(route_map)
                
                # Create routes with different colored animated segments
                all_coords = [post_office_coords] + adjusted_coords + [post_office_coords]
                total_duration = 0
                total_distance = 0
                
                # Get route for each segment separately
                for i in range(len(all_coords) - 1):
                    route_data = get_optimized_route(all_coords, i)
                    
                    if route_data and 'routes' in route_data and route_data['routes']:
                        route = route_data['routes'][0]
                        
                        if 'geometry' in route:
                            route_coords = polyline.decode(route['geometry'])
                            color = route_colors[i % len(route_colors)]
                            
                            # Convert coordinates to the format needed for AntPath
                            path_coords = [[lat, lon] for lat, lon in route_coords]
                            
                            # Create animated route segment
                            plugins.AntPath(
                                locations=path_coords,
                                color=color,
                                weight=3,
                                opacity=0.8,
                                popup=f"Route Segment {i+1}",
                                delay=1000,  # Animation speed (milliseconds)
                                dash_array=[10, 20],  # Pattern of the animated line
                                pulse_color='#FFFFFF'  # Color of the animated pulse
                            ).add_to(route_map)
                            
                            # Add to totals
                            if 'duration' in route:
                                total_duration += route['duration']
                            if 'distance' in route:
                                total_distance += route['distance']
                
                # Display map in left column
                with col1:
                    st_folium(route_map, width=800, height=600)
                
                # Display route information in right column
                with col2:
                    st.write("### Route Details")
                    st.write("**Start:** Post Office 🏠")
                    for idx, addr in enumerate(delivery_addresses, 1):
                        st.write(f"**Stop {idx}:** {addr}")
                    st.write("**End:** Post Office 🏠")
                    
                    hours = total_duration // 3600
                    minutes = (total_duration % 3600) // 60
                    st.metric("Estimated Duration", f"{int(hours)}h {int(minutes)}m")
                    
                    distance_km = total_distance / 1000
                    st.metric("Total Distance", f"{distance_km:.1f} km")
                    
                    st.write("### Summary")
                    st.metric("Total Stops", len(delivery_coords))
                    
                    st.info("The routes are animated with a 'marching ants' effect to show the delivery path.")
            
            else:
                st.error("No valid delivery locations found")
        else:
            st.error("Unable to locate post office")

if __name__ == "__main__":
    main()