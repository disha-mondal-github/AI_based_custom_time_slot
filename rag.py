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

load_dotenv()

# Connect to MongoDB
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

# Cache for VectorStoreIndex
INDEX_CACHE_DIR = Path("./cache")
INDEX_CACHE_DIR.mkdir(exist_ok=True)

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

def display_delivery_schedule(deliveries):
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
                if st.checkbox('Mark as Delivered', key=key, 
                             help="Click to confirm delivery"):
                    if update_delivery_status(delivery['_id'], 'Delivered'):
                        st.success(f"Delivery {delivery['Booking ID']} marked as delivered!")
                        # Clear the cached data to force a refresh
                        st.cache_data.clear()
                        time.sleep(0.5)  # Small delay to ensure DB update completes
                        st.experimental_rerun()
                    else:
                        st.error("Failed to update delivery status")
            else:
                st.write("✅ Delivered")
        
        st.markdown("---")

def main():
    st.title("Postman Delivery Schedule")
    
    # Initialize models at startup
    init_models()
    
    postman_id = st.text_input("Enter Postman ID")
    delivery_date = st.date_input("Enter Delivery Date", min_value=datetime.today())

    if st.button("Get Schedule"):
        with st.spinner("Generating schedule..."):
            delivery_date_str = delivery_date.strftime("%Y-%m-%d")
            deliveries, postman = fetch_deliveries(postman_id, delivery_date_str)
            
            if postman:
                st.write("### Postman Details")
                st.write(f"**Name:** {postman['postman_name']}")
                st.write(f"**Phone Number:** {postman['postman_phn_no']}")
                st.write(f"**Post Office:** {postman['post_office']}")
                
                if deliveries:
                    st.write("### Delivery Schedule")
                    sorted_deliveries = get_optimal_order_rag(deliveries)
                    display_delivery_schedule(sorted_deliveries)
                else:
                    st.write("No deliveries found for the given date.")
            else:
                st.write("Postman ID not found.")

if __name__ == "__main__":
    main()