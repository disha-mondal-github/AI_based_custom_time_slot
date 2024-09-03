import streamlit as st
from pymongo import MongoClient
from datetime import datetime
from llama_index.core import VectorStoreIndex, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# Connect to MongoDB
client = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["DeliverySystem"]
recipients_collection = db["recipient"]
postman_collection = db["postmen"]

# Set up LlamaIndex and Ollama
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
Settings.llm = Ollama(model="llama3", request_timeout=360.0)

def get_postman_details(postman_id):
    postman = postman_collection.find_one({"postman_id": postman_id})
    if postman:
        return {
            "postman_name": postman.get("postman_name"),
            "postman_phn_no": postman.get("postman_phn_no"),
            "post_office": postman.get("post_office")
        }
    else:
        return None

def fetch_deliveries(postman_id, delivery_date):
    postman = get_postman_details(postman_id)
    
    if not postman:
        return [], None
    
    post_office = postman['post_office']
    formatted_date = datetime.strptime(delivery_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    
    deliveries = recipients_collection.find({
        "Receiver Post Office": post_office,
        "Date of Delivery": formatted_date
    })
    
    delivery_list = list(deliveries)
    
    return delivery_list, postman

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

def main():
    st.title("Postman Delivery Schedule")
    
    postman_id = st.text_input("Enter Postman ID")
    delivery_date = st.date_input("Enter Delivery Date", min_value=datetime.today())

    if st.button("Get Schedule"):
        delivery_date_str = delivery_date.strftime("%Y-%m-%d")
        deliveries, postman = fetch_deliveries(postman_id, delivery_date_str)
        
        if postman:
            st.write(f"**Postman Name:** {postman['postman_name']}")
            st.write(f"**Postman Phone Number:** {postman['postman_phn_no']}")
            st.write(f"**Post Office:** {postman['post_office']}")
            
            if deliveries:
                st.write("**Schedule:**")
                sorted_deliveries = get_optimal_order_rag(deliveries)
                for i, delivery in enumerate(sorted_deliveries, 1):
                    st.write(f"{i}. {delivery}")
            else:
                st.write("No deliveries found for the given date.")
        else:
            st.write("Postman ID not found.")

if __name__ == "__main__":
    main()
