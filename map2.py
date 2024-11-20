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
    Geocoding function that returns coordinates for any valid address with fallback options.
    If exact address isn't found, attempts to find closest possible match.
    
    Args:
        address: The address string to geocode
        original_address: The original input address for reference
    
    Returns:
        Tuple containing coordinates [lon, lat] and matched address, or (None, None) if no match found
    """
    url = "https://api.mapbox.com/geocoding/v5/mapbox.places/"
    base_params = {
        'access_token': ACCESS_TOKEN,
        'country': 'IN',
        'bbox': DELHI_BBOX,
        'proximity': '77.2,28.5'  # Center of Delhi
    }
    
    def try_geocoding(query: str, params: dict) -> Tuple[Optional[List[float]], Optional[str], Optional[str]]:
        try:
            response = requests.get(f"{url}{query}.json", params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'features' in data and data['features']:
                feature = data['features'][0]
                coords = feature['geometry']['coordinates']
                matched_place = feature['place_name']
                return coords, matched_place, None
            return None, None, "No features found"
        except requests.exceptions.RequestException as e:
            return None, None, str(e)

    # Clean and standardize address
    address = (address.upper()
              .replace("SAHAPUR", "SHAHPUR")
              .replace("  ", " ")
              .strip())
    
    # Try with full address first
    params = {**base_params, 'limit': 1, 'types': 'address,poi,place'}
    coords, matched_address, error = try_geocoding(address, params)
    if coords:
        return coords, matched_address

    # Extract main landmarks and areas
    main_areas = [
        "SHAHPUR JAT", "KALKAJI", "GAUTAM NAGAR", "SOUTH EXTENSION",
        "HAUZ KHAS", "ANDREWS GANJ", "MASJID MOTH", "GREEN PARK"
    ]
    
    # Try to find the main area in the address
    found_areas = [area for area in main_areas if area in address]
    if found_areas:
        for area in found_areas:
            # Try with area name + New Delhi
            query = f"{area}, New Delhi"
            coords, matched_address, error = try_geocoding(query, params)
            if coords:
                st.warning(f"Using approximate location for: {original_address}")
                return coords, matched_address
    
    # If still no match, try breaking down the address
    address_parts = address.split(',')
    for part in address_parts:
        part = part.strip()
        if len(part) > 5:  # Avoid very short fragments
            # Try with broader search
            params = {**base_params, 'limit': 1, 'types': 'poi,place,locality,neighborhood'}
            coords, matched_address, error = try_geocoding(f"{part}, Delhi", params)
            if coords:
                st.warning(f"Using broader location match for: {original_address}")
                return coords, matched_address
    
    # Last resort: Try to match with postal code if present
    postal_codes = [code.strip() for code in address.split() if code.strip().isdigit() and len(code.strip()) == 6]
    if postal_codes:
        params = {**base_params, 'limit': 1, 'types': 'postcode'}
        coords, matched_address, error = try_geocoding(f"{postal_codes[0]}, Delhi", params)
        if coords:
            st.warning(f"Using postal code location for: {original_address}")
            return coords, matched_address
    
    st.error(f"Failed to find any location match for: {original_address}")
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