from llama_index import VectorStoreIndex  # Make sure this is the correct import path for VectorStoreIndex

# Define the Document class
class Document:
    def __init__(self, id_, content):
        self.id_ = id_
        self.content = content

    def get_doc_id(self):
        return self.id_

# Function to convert delivery data to Document objects
def convert_to_documents(deliveries):
    documents = []
    for delivery in deliveries:
        doc_id = delivery.get('Booking ID')
        content = delivery  # or you can format it as needed
        documents.append(Document(doc_id, content))
    return documents

# Example delivery data
deliveries = [
    {'_id': '66d1f86ffd44e36c2ebf3b26', 'Booking ID': 'YKK5UMLM', 'Sender Name': 'Kaira Sengupta', 'Sender Gmail ID': 'kairasengupta214@gmail.com', 'Receiver Name': 'Trisha Deo', 'Receiver Gmail ID': 'trishadeo248@gmail.com', 'Receiver Address': 'INDISH - The Art Of Mughlai Food, 39, First Floor, DDA Auto Complex, Zamrudpur, Greater Kailash 1 (GK 1), New Delhi, 110049', 'Receiver Post Office': 'Andrews Ganj', 'Zipcode': '110049', 'Receiver Phone Number': '3012533847', 'Order Date': '2024-08-28', 'Date of Delivery': '2024-10-12', 'Time Slot of Delivery': '11:08 AM - 11:38 AM', 'Equipment Getting Delivered': 'Letters', 'Delivery Status': 'Not Delivered'},
    {'_id': '66d1f86ffd44e36c2ebf3b31', 'Booking ID': 'OJD7OWXN', 'Sender Name': 'Raghav Uppal', 'Sender Gmail ID': 'raghavuppal345@gmail.com', 'Receiver Name': 'Sahil Khurana', 'Receiver Gmail ID': 'sahilkhurana918@gmail.com', 'Receiver Address': "PARAM'S SWEETS & SNACKS SHOP, N H NO-169, G/F , FRONT PORTION SHAHPUR JATT , SAHAPUR JAT , HAUZ KHAS, South , Delhi - 110049", 'Receiver Post Office': 'Andrews Ganj', 'Zipcode': '110049', 'Receiver Phone Number': '5742395136', 'Order Date': '2024-08-28', 'Date of Delivery': '2024-10-12', 'Time Slot of Delivery': '02:08 PM - 02:38 PM', 'Equipment Getting Delivered': 'Clothing', 'Delivery Status': 'Not Delivered'},
    {'_id': '66d1f86ffd44e36c2ebf3b71', 'Booking ID': 'GAKHGW9D', 'Sender Name': 'Ivan Sanghvi', 'Sender Gmail ID': 'ivansanghvi660@gmail.com', 'Receiver Name': 'Lakshay Jayaraman', 'Receiver Gmail ID': 'lakshayjayaraman624@gmail.com', 'Receiver Address': 'Sharma Ji Ke Mashoor Chole Bhature, Outside 211a , masjid modh, leela ram market, MASJID MOTH, HAUZ KHAS, South , Delhi - 110049', 'Receiver Post Office': 'Andrews Ganj', 'Zipcode': '110049', 'Receiver Phone Number': '3504632452', 'Order Date': '2024-08-28', 'Date of Delivery': '2024-10-12', 'Time Slot of Delivery': '10:47 AM - 11:17 AM', 'Equipment Getting Delivered': 'Articles', 'Delivery Status': 'Not Delivered'}
]

# Convert to Document objects
documents = convert_to_documents(deliveries)

# Create the VectorStoreIndex
try:
    index = VectorStoreIndex.from_documents(documents)
    print("Index created successfully.")
except AttributeError as e:
    print(f"AttributeError: {e}")
    print("Ensure that documents are instances of the Document class and have the necessary attributes.")
