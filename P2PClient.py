import socket
import argparse
import threading
import sys
import hashlib
import time
import logging
import os


#TODO: Implement P2PClient that connects to P2PTracker


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument('-folder', type=str, required=True)
	parser.add_argument('-transfer_port')
	parser.add_argument('-name')
	args = parser.parse_args()

	FOLDER = args.folder
	TRANSFER_PORT = int(args.transfer_port)
	NAME = args.name
	SERVER_HOST = 'localhost'
	SERVER_PORT = 5100

	logger = logging.getLogger()
	logging.basicConfig(filename="logs.log", format="%(message)s", level=logging.INFO)

	def request_listener():
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ps:
			ps.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # solves common issue from Edstem
			ps.bind(('localhost', TRANSFER_PORT))
			ps.listen(1)

			while True:
				snd_peer_socket, _ = ps.accept()
				with snd_peer_socket:
					try:
						peer_message = snd_peer_socket.recv(1024).decode()
					except:
						continue

					# Preprocess peer message
					split_peer_message = peer_message.split(',')

					if split_peer_message[0] == "REQUEST_CHUNK": # REQUEST_CHUNK,<chunk_index>
						requested_chunk_index = split_peer_message[1]

						# Read local chunks
						with open(f"{FOLDER}/local_chunks.txt", 'rt') as f:
							local_chunks = f.read().split("\n")
						
						# Find the correct file
						for chunk_line in local_chunks[:-1]:
							chunk_index, local_file = tuple(chunk_line.split(',')) # <chunk_index>,<local_filename>
							if chunk_index == requested_chunk_index:
								# Save the requested file name
								local_file_path = f"{FOLDER}/{local_file}"
								break
						
						# Send the requested file partially
						with open(local_file_path, 'rb') as f:
							while True:
								file_data = f.read(1024) # Read 1KB of data from the file
								if not file_data:
									break # End of file
								try:
									snd_peer_socket.sendall(file_data)
								except:
									raise Exception("sending file to peer failed")
					# else:
	  				# 	pass
						# This should never occur
						# print("WEIRD MESSAGE:", peer_message)
						# raise Exception(f"Peer sent a weird message: {peer_message}")

	# initiate a thread for listening to other client requests
	listener_thread = threading.Thread(target=request_listener)
	listener_thread.start()

	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
		server_socket.connect((SERVER_HOST, SERVER_PORT))
		# .setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	
		# Read local chunks
		with open(f"{FOLDER}/local_chunks.txt") as f:
			local_chunks = f.read().split("\n")
		if local_chunks[-1] == '': del local_chunks[-1]
		
		# Create variables for tracking
		chunk_count = local_chunks[-1].split(',')[0] # <num_of_chunks>,LASTCHUNK
		missing_chunks = list(range(1,int(chunk_count)+1))

		# Announce existing chunks to server/tracker
		for chunk_line in local_chunks[:-1]:
			chunk_index = chunk_line.split(',')[0] # <chunk_index>,<local_filename>
			missing_chunks.remove(int(chunk_index)) # update missing_chunks for later use
			message = f"LOCAL_CHUNKS,{chunk_index},localhost,{TRANSFER_PORT}"
			try:
				server_socket.send(message.encode())
				logger.info(f"{NAME},{message}")
				time.sleep(1)
			except:
				# This should never happen
				raise Exception("Client couldn't announce local chunks to server")
		
		# Ask about missing chunk location and request them
		while len(missing_chunks) > 0:
			chunk_index = missing_chunks.pop(0)
			message = f"WHERE_CHUNK,{chunk_index}"
			try:
				server_socket.send(message.encode())
				server_response = server_socket.recv(1024).decode()
				logger.info(f"{NAME},{message}")
			except:
				break # if the server is broken, end everything

			print("SERVER RESPONSE:", server_response)
			split_server_response = server_response.split(',')

			if split_server_response[0] == "GET_CHUNK_FROM": # GET_CHUNK_FROM,<chunk_index>,<IP_address1>,<Port_number1>,<IP_address2>,<Port_number2>,...
				chunk_obatained = False
				for i in range(2, len(split_server_response), 2): # Find a valid peer
					ip_addr = split_server_response[i]
					port_num = int(split_server_response[i+1])
					with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as req_peer_socket:
						try:
							req_peer_socket.connect((ip_addr, int(port_num)))
							peer_message = f"REQUEST_CHUNK,{chunk_index}"
							req_peer_socket.send(peer_message.encode())
							logger.info(f"{NAME},REQUEST_CHUNK,{chunk_index},{ip_addr},{port_num}")

							# Receive file chunks and save partially
							with open(f"{FOLDER}/chunk_{chunk_index}", 'wb') as f:
								while True:	
									file_chunk = req_peer_socket.recv(1024)  # Receive 1KB of data
									if not file_chunk:
										break  # End of file
									f.write(file_chunk)
							
							# peer_response = req_peer_socket.recv(4096) # no need to decode file data
							
							# Save file locally
							# with open(f"{FOLDER}/chunk_{chunk_index}", 'wb') as f:
							# 	f.write(peer_response)

							# Update local_chunks.txt
							with open(f"{FOLDER}/local_chunks.txt", 'rt') as f:
								text = f.read()
							updated_text = f"{chunk_index},chunk_{chunk_index}\n{text}" # <chunk_index>,<local_filename>
							with open(f"{FOLDER}/local_chunks.txt", 'wt') as f:
								f.write(updated_text)
							
							chunk_obatained = True
							break # Chunk obrained successfully
						except:
							if i + 2 >= len(split_server_response): # check if it's the last iteration
								missing_chunks.append(chunk_index)
				
				# Inform the server of the update
				if chunk_obatained:
					try:
						message = f"LOCAL_CHUNKS,{chunk_index},localhost,{TRANSFER_PORT}"
						server_socket.send(message.encode())
						logger.info(f"{NAME},{message}")
					except:
						raise Exception("Client couldn't update new local chunk to server")
			elif split_server_response[0] == "CHUNK_LOCATION_UNKNOWN": # CHUNK_LOCATION_UNKNOWN,<chunk_index>
				missing_chunks.append(chunk_index)
				# time.sleep(1)
