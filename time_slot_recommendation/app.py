from flask import Flask, request, render_template
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier

# Initialize the Flask app
app = Flask(__name__)

# Load the dataset
df = pd.read_csv('receiver_timeslots.csv')

# Encode the 'Receiver Name' and 'Time Slot' columns
label_encoder_name = LabelEncoder()
label_encoder_slot = LabelEncoder()

df['Receiver Name Encoded'] = label_encoder_name.fit_transform(df['Receiver Name'])
df['Time Slot Encoded'] = label_encoder_slot.fit_transform(df['Time Slot'])

# Prepare the feature matrix X and target vector y
X = df[['Receiver Name Encoded']]
y = df['Time Slot Encoded']

# Train the RandomForestClassifier
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X, y)

# Define the prediction function
def predict_time_slot(user_name):
    user_name_encoded = label_encoder_name.transform([user_name])
    predicted_slot_encoded = model.predict([user_name_encoded])[0]
    predicted_slot = label_encoder_slot.inverse_transform([predicted_slot_encoded])[0]
    return predicted_slot

# Define the home route
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        user_name = request.form['user_name']
        predicted_time_slot = predict_time_slot(user_name)
        return render_template('result.html', user_name=user_name, predicted_time_slot=predicted_time_slot)
    return render_template('index.html')

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
