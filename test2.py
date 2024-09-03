from pymongo import MongoClient
from datetime import datetime
from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama

# MongoDB Connection
client = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["DeliverySystem"]
recipients_collection = db["recipient"]
postman_collection = db["postmen"]

# Constants
GEOAPIFY_API_KEY = "2c66eb88f80b40299cf87f96c7f8228c"

# Fetch Post Office
def get_post_office(postman_id):
    postman = postman_collection.find_one({"postman_id": postman_id})
    if postman:
        return postman.get("post_office")
    else:
        print(f"Postman with ID {postman_id} not found.")
        return None

# Fetch Deliveries
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

# Prepare Data for RAG
def prepare_data_for_rag(deliveries):
    data = []
    for delivery in deliveries:
        text = f"Booking ID: {delivery.get('Booking ID')}, Address: {delivery.get('Receiver Address')}, Time Slot: {delivery.get('Time Slot of Delivery')}"
        data.append(text)
    return data

# RAG Configuration
def setup_rag():
    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
    Settings.llm = Ollama(model="llama3", request_timeout=360.0)

# RAG Implementation
def get_optimal_order_rag(deliveries):
    # Prepare and index data directly from MongoDB
    data = prepare_data_for_rag(deliveries)
    
    # Use MongoDB directly for indexing and querying
    documents = [{"text": item} for item in data]
    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine()

    # Query to get the optimal order
    query = "Provide the optimal delivery order based on time slots."
    response = query_engine.query(query)
    return response

# Main function
def main(postman_id, delivery_date):
    deliveries = fetch_deliveries(postman_id, delivery_date)
    if deliveries:
        setup_rag()
        optimal_order = get_optimal_order_rag(deliveries)
        print(f"Optimal Delivery Order: {optimal_order}")
    else:
        print("No deliveries to process.")

# Example Usage
postman_id = "ZLT7WU"  # Replace with actual Postman ID
delivery_date = "2024-10-12"  # Replace with desired date
main(postman_id, delivery_date)
