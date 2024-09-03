from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama

# Load documents from the 'data' directory
documents = SimpleDirectoryReader("data").load_data()

# Set the embedding model (BGE-base in this case)
embedding_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")

# Configure Ollama LLM with the 'llama3' model
llm = Ollama(model="llama3", request_timeout=360.0)

# Create a ServiceContext with the embedding model and LLM
service_context = ServiceContext.from_defaults(embed_model=embedding_model, llm=llm)

# Create the index from the documents using the service context
index = VectorStoreIndex.from_documents(documents, service_context=service_context)

# Create a query engine from the index
query_engine = index.as_query_engine()

# Perform a query and get the response
response = query_engine.query("What did the author do growing up?")

# Print the response
print(response)
