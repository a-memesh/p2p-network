import socket
import threading
import sys
import hashlib
import time
import logging


#TODO: Implement P2PTracker


if __name__ == "__main__":
	HOST = 'localhost'
	PORT = 5100

	chunk_list = {} # {chunk_index: [(IP_address, Port_number), ... ()]}
	chunk_list_lock = threading.Lock()
	closing_threads = []
	closing_threads_lock = threading.Lock()

	logger = logging.getLogger()
	logging.basicConfig(filename="logs.log", format="%(message)s", level=logging.INFO)

	def client_handler(client_socket: socket.socket):
		with client_socket:
			while True:
				try:
					client_message = client_socket.recv(1024).decode()
				except:
					break

				# Preprocess client message
				split_client_message = client_message.split(',')
				client_command = split_client_message[0] # either LOCAL_CHUNKS or WHERE_CHUNK
				chunk_index = split_client_message[1] # it's string variable

				# Handle different commands
				if client_command == "LOCAL_CHUNKS": # LOCAL_CHUNKS,<chunk_index>,<IP_address>,<Port_number>
					# Update chunk_list
					with chunk_list_lock:
						if chunk_index in chunk_list:
							chunk_list[chunk_index].append(tuple(split_client_message[2:])) # (IP_address, Port_number)
						else:
							chunk_list[chunk_index] = [tuple(split_client_message[2:])]
				elif client_command == "WHERE_CHUNK": # WHERE_CHUNK,<chunk_index>
					# Query chunk_list
					with chunk_list_lock:
						if chunk_index in chunk_list:
							response = f"GET_CHUNK_FROM,{chunk_index}"
							for ip_addr, port_num in chunk_list[chunk_index]:
								response = f"{response},{ip_addr},{port_num}"
						else:
							response = f"CHUNK_LOCATION_UNKNOWN,{chunk_index}"
					
					try:
						client_socket.send(response.encode())
						logger.info(f"P2PTracker,{response}")
					except:
						break
		
		# add to closing_threads
		with closing_threads_lock:
			closing_threads.append(threading.current_thread())

	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # solves common issue from Edstem
		s.bind((HOST, PORT))
		s.listen(1)
		
		while True:
			client_socket, _ = s.accept() # blocking

			# Close threads
			if len(closing_threads) > 0:
				with closing_threads_lock:
					for thread in closing_threads:
						thread.join()

			# initiate a thread for handling clients and implementing the logic for responding
			client_thread = threading.Thread(target=client_handler, args=[client_socket])
			client_thread.start()
