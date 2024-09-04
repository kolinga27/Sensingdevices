"""
ESP32 Datalogger - Client

Description:
This Python program interfaces with an ESP32 microcontroller to log sensor data 
and transmit it over Bluetooth. It includes functionality to update graphs in real-time 
and store received data in a CSV file.

Author:
Blaine Wu

Date:
2024-07-24

Version:
1.4

Changes in Version 1.4:
- Automatic resistance conversion from voltage
- Pop-up error notifications

Notes:
- Requires Kivy, PyBluez, and Python 3.x.
- Ensure ESP32 is properly configured for Bluetooth communication.
- Program is currently limited to ~2000 datapoints before UI becomes laggy.

Connections:
- ESP32 Bluetooth module connected to the host via RFCOMM.
- Sensors connected to ESP32 GPIO pins for data acquisition.
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import mainthread
from kivy.garden.graph import Graph, MeshLinePlot
from kivy.metrics import dp
import threading
import bluetooth
import csv
from datetime import datetime
import os
import json

class MyGrid(Widget):
    pass

class DataLogger(App):
    def build(self):
        return MyGrid()

    def on_start(self):
        self.last_received_time = 0
        self.graph_count = 0
        self.graph_info = []  # List of Dictionaries to hold graph information
        self.connected = False  # Flag to track Bluetooth connection status

        self.start_timestamp = datetime.now().strftime('%Y-%m-%d_T_%H_%M_%S')
        self.filename = f'Data_Log_{self.start_timestamp}.csv'
    
    def button_create_graph(self):
        try:
            graph_name = self.root.ids.graph_name_input.text
            axis_limit = int(self.root.ids.reference_input.text)  # Attempt to convert input to integer
            graph_type = self.root.ids.type_dropdown_spinner.text
            self.create_graph(graph_name, axis_limit, graph_type)
        except ValueError:
            print("Invalid input for axis limit. Please enter a valid integer.")
            self.show_popup("Input Error", "Invalid input for axis limit. Please enter a valid integer.")

    def create_graph(self, graph_name, axis_limit, graph_type):
        graphs_container = self.root.ids.graphs_container
        graph = Graph(
            size_hint=(1, None),
            height=dp(300),  # Adjust height as needed
            xlabel='Time',
            ylabel=graph_name,
            x_ticks_minor=5,
            x_ticks_major=100,
            y_ticks_minor=5,
            y_ticks_major=int(axis_limit / 4),
            y_grid_label=True,
            x_grid_label=True,
            padding=5,
            xmin=0,
            xmax=100,
            ymin=0,
            ymax=axis_limit
        )
        plot = MeshLinePlot(color=[1, 0, 0, 1])  # Red color plot
        graph.add_plot(plot)
        graphs_container.add_widget(graph)  # Display new Graph
        self.graph_info.append({'name': graph_name, 'axis_limit': axis_limit, 'graph_type': graph_type})  # Update data structure
        self.graph_count += 1
        self.root.ids.graph_name_input.text = ''
        self.root.ids.reference_input.text = ''
    
    def connect(self):
        self.target_address = "D4:D4:DA:54:6B:D6"  # Replace with your ESP32's Bluetooth MAC address
        self.port = 1  # Standard port for Bluetooth communication
        try:
            self.sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.sock.connect((self.target_address, self.port))
            self.connected = True  # Update the connection status
            print("Connected to ESP32 over Bluetooth")
            self.update_BTconnection_textbox("Connected to ESP32!")
            self.start_receiving_thread()  # Start receiving thread after successful connection
        except Exception as e:
            self.connected = False  # Update the connection status
            print(f"Error Connecting: {e}")
            self.update_BTconnection_textbox(f"Error Connecting: {e}")

    def send_string_over_bluetooth(self, message):
        if self.connected:
            try:
                self.sock.send(message.encode())  # Ensure message is encoded properly
                print(f"Sent message over Bluetooth: {message}")
            except Exception as e:
                self.connected = False  # Update the connection status
                print(f"Error sending message over Bluetooth: {e}")
                self.update_BTconnection_textbox(f"Error sending message: {e}")
        else:
            print("Not connected to Bluetooth")
            self.update_BTconnection_textbox("Not connected to Bluetooth")

    def receive_messages(self):
        self.buffer = ""  # Buffer to hold incomplete data
        try:
            while self.connected:
                data = self.sock.recv(4096).decode()
                if not data:
                    self.connected = False  # Update the connection status
                    self.update_BTconnection_textbox("Bluetooth connection lost")
                    self.show_popup("Bluetooth Connection Lost", "Bluetooth connection lost")
                    break
                self.buffer += data  # Append new data to the buffer
                while '\n' in self.buffer:  # Check if there is a complete message
                    line, self.buffer = self.buffer.split('\n', 1)  # Extract the line and update the buffer
                    self.update_data_textbox(line)
                    print(line)
                    self.update_graph(line)  # Update graph with received data
                    self.store_to_csv(line)  # Store data to CSV
        except Exception as e:
            self.connected = False  # Update the connection status
            print(f"Error receiving message over Bluetooth: {e}")
            self.update_BTconnection_textbox(f"Error receiving message: {e}")

    @mainthread
    def update_data_textbox(self, message):
        # Update TextInput widget with received message
        self.root.ids.data_textbox.text += f"{message}\n"
        
    @mainthread
    def update_BTconnection_textbox(self, message):
        # Update TextInput widget with received message
        self.root.ids.BTconnection_textbox.text = f"{message}\n"

    @mainthread
    def update_graph(self, data):
        # Parse the received data and update the graph
        try:
            values = data.strip().split(',')
            if len(values) == 5:
                time = int(values[0])
                
                # Check if this is a new time point or a repeat
                if time > self.last_received_time:
                    for i in range(self.graph_count):
                        graph = self.root.ids.graphs_container.children[-(i + 1)]
                        plot = graph.plots[0]  # Assuming the plot is the first child widget
                        
                        if self.graph_info[i]["graph_type"] == "Resistance":
                            y = (float(values[i + 1]) * self.graph_info[i]["axis_limit"]) / (3.3 - float(values[i + 1]))
                        else:
                            y = float(values[i + 1])
                            
                        plot.points.append((time, y))
                        # Ensure the graph limits are correctly typed before comparison
                        new_max_x = max(int(graph.xmax), time)
                        graph.xmax = new_max_x
                        graph.x_ticks_major = int(new_max_x / 4)
                        
                        if y > int(graph.ymax):
                            new_max_y = max(int(graph.ymax), y) * 1.1
                            graph.ymax = new_max_y
                            graph.y_ticks_major = int(new_max_y / 4)

                    # Update the last received time
                    self.last_received_time = time
            else:
                print(f"Ignoring data: {data.strip()}")  # Print or log the inconsistent data for debugging
        except ValueError as ve:
            print(f"ValueError: {ve}, Data: {data.strip()}")  # Print or log the ValueError for debugging
        except Exception as e:
            print(f"Error updating graph: {e}")

    def store_to_csv(self, data):
        try:
            save_dir = "Saved_Data"
            os.makedirs(save_dir, exist_ok=True)  # Create directory if it doesn't exist
            with open(f'Saved_Data/{self.filename}', mode='a', newline='') as file:
                writer = csv.writer(file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(data.strip().split(','))
        except Exception as e:
            print(f"Error storing data to CSV: {e}")

    def start_receiving_thread(self):
        receive_thread = threading.Thread(target=self.receive_messages)
        receive_thread.daemon = True  # Daemonize the receive thread so it automatically dies when the main program ends
        receive_thread.start()
        
    def save_graph_config(self):
        save_name = self.root.ids.save_graph_config_name.text
        configurations = {}

        # Load existing configurations if the file exists
        try:
            with open('configurations.json', 'r') as f:
                configurations = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("Creating new configurations file or handling invalid JSON.")

        # Add the current graph_info list to the configurations
        configurations[save_name] = self.graph_info

        # Write the updated configurations back to the file
        with open('configurations.json', 'w') as f:
            json.dump(configurations, f, indent=4)
    
    def load_graph_config(self):
        try:
            with open('configurations.json', 'r') as f:
                configurations = json.load(f)
                save_name = self.root.ids.load_graph_config_name.text
                if save_name in configurations:
                    self.reset_graphs()  # Clear existing graphs before loading new configuration
                    save = configurations[save_name]
                    print(save)
                    for graph_data in save:
                        print(graph_data)
                        name = graph_data.get('name')
                        axislim = int(graph_data.get('axis_limit'))
                        graph_type = graph_data.get('graph_type')
                        self.create_graph(name, axislim, graph_type)
                else:
                    print(f"Error: Save name '{save_name}' not found in configurations")
                    self.show_popup("Save Not Found", f"Save name '{save_name}' not found.")
        except (FileNotFoundError, json.JSONDecodeError):
            print("Error: configurations.json not found or invalid JSON")

    def reset_graphs(self):
        self.root.ids.graphs_container.clear_widgets()  # Clear existing graphs
        self.graph_info = []  # Clear the graph info list
        self.graph_count = 0
        self.last_received_time = 0
        
    def toggle_on_autoupdate(self):
        self.send_string_over_bluetooth("TOGGLE ON AUTOUPDATE")
        
    def toggle_off_autoupdate(self):
        self.send_string_over_bluetooth("TOGGLE OFF AUTOUPDATE")
        
    def on_spinner_select(self, selected_type):
        if selected_type == "Resistance":
            self.root.ids.reference_input.readonly = False
            self.root.ids.reference_input.hint_text = "Input Baseline Resistance"
            self.root.ids.reference_input.text = ""
        elif selected_type == "Voltage":
            self.root.ids.reference_input.readonly = True
            self.root.ids.reference_input.text = "4"
        elif selected_type == "Raw ADC Val":
            self.root.ids.reference_input.readonly = True
            self.root.ids.reference_input.text = "5000"
        elif selected_type == "DHT11 Temperature":
            self.root.ids.reference_input.readonly = True
            self.root.ids.reference_input.text = "40"
        elif selected_type == "DHT11 Humidity":
            self.root.ids.reference_input.readonly = True
            self.root.ids.reference_input.text = "100"
        else:
            self.root.ids.reference_input.readonly = True
            self.root.ids.reference_input.hint_text = "N/A"
            
    def show_popup(self, title, message):
        content = BoxLayout(orientation='vertical')
        message_label = Label(text=message)
        close_button = Button(text='Close', size_hint=(1, 0.2))
        
        content.add_widget(message_label)
        content.add_widget(close_button)
        
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.4))
        close_button.bind(on_release=popup.dismiss)
        popup.open()
                    
if __name__ == '__main__':
    DataLogger().run()
