import os
from PIL import Image
from flask import Flask, render_template, request
import concurrent.futures
import threading
from datetime import datetime
import queue

app = Flask(__name__)

# Dictionaries to store thread information
resize_thread_info = {}
classify_thread_info = {}

# Queue to store resized images for classification
classification_queue = queue.Queue()

def resize_image(image_path, output_path, new_size):
    thread_id = threading.current_thread().ident
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - Thread {thread_id}: Resizing image {image_path}")

    # Record start timestamp for resizing
    start_time = datetime.now()

    img = Image.open(image_path)
    resized_img = img.resize(new_size)
    resized_img.save(output_path)

    # Record end timestamp for resizing
    end_time = datetime.now()

    # Update resize_thread_info
    if thread_id not in resize_thread_info:
        resize_thread_info[thread_id] = {"images_processed": 0, "total_duration": 0}
    resize_thread_info[thread_id]["images_processed"] += 1
    resize_thread_info[thread_id]["total_duration"] += (end_time - start_time).total_seconds()

    # Add resized image to the classification queue
    classification_queue.put((output_path, img.size))

def classify_images_from_queue(results):
    while True:
        try:
            # Retrieve resized image from the queue
            image_path, size = classification_queue.get(timeout=1)
        except queue.Empty:
            break  # Break if the queue is empty

        thread_id = threading.current_thread().ident
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} - Thread {thread_id}: Classifying image {image_path}")

        # Record start timestamp for classification
        start_time = datetime.now()

        # Update classify_thread_info
        if thread_id not in classify_thread_info:
            classify_thread_info[thread_id] = {"images_processed": 0, "total_duration": 0}
        classify_thread_info[thread_id]["images_processed"] += 1

        # Classify
        size_class = classify_size(size)
        color_class = classify_color(Image.open(image_path))
        pixels_class = classify_pixels(size)

        result = {"filename": os.path.basename(image_path), "size_class": size_class, "color_class": color_class, "pixels_class": pixels_class}

        # Add the result to the list
        results.append(result)

        # Record end timestamp for classification
        end_time = datetime.now()

        classify_thread_info[thread_id]["total_duration"] += (end_time - start_time).total_seconds()
            # Save classified image to a directory based on pixel class
        classified_dir = os.path.join("static/classified", color_class)
        os.makedirs(classified_dir, exist_ok=True)
        output_path = os.path.join(classified_dir, os.path.basename(image_path))
        Image.open(image_path).save(output_path)
    
        # Remove the image from the resized directory
        os.remove(image_path)

def classify_size(size):
    if max(size) >= 1000:
        return "Large"
    elif max(size) >= 500:
        return "Medium"
    else:
        return "Small"

def classify_color(img):
    average_color = tuple(map(int, img.resize((1, 1)).getpixel((0, 0))))
    if max(average_color) > 200:
        return "Bright"
    elif max(average_color) > 100:
        return "Moderate"
    else:
        return "Dark"

def classify_pixels(size):
    pixel_count = size[0] * size[1]
    if pixel_count >= 1000000:
        return "High Resolution"
    elif pixel_count >= 500000:
        return "Medium Resolution"
    else:
        return "Low Resolution"

def process_images_in_folder(folder_path):
    results = []

    # Record start timestamp for overall processing
    overall_start_time = datetime.now()

    # Use a ThreadPoolExecutor for parallel processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(resize_image, os.path.join(folder_path, file), os.path.join("static/resized", file), (200, 200)): file for file in os.listdir(folder_path) if file.lower().endswith(('.png', '.jpg', '.jpeg'))}

    # Start a separate thread for classification from the queue
    classification_thread = threading.Thread(target=classify_images_from_queue, args=(results,))
    classification_thread.start()

    # Wait for all resize tasks to complete
    concurrent.futures.wait(futures)

    # Wait for the classification thread to finish
    classification_thread.join()
    print("\nThread Information:")
    print("Resizing Threads:")
    for thread_id, info in resize_thread_info.items():
        print(f"Thread {thread_id}: {info['images_processed']} images processed during resizing, total duration: {info['total_duration']} seconds")
    resize_thread_info.clear()

    print("\nClassifying Threads:")
    for thread_id, info in classify_thread_info.items():
        print(f"Thread {thread_id}: {info['images_processed']} images processed during classification, total duration: {info['total_duration']} seconds")
    classify_thread_info.clear()


    # Record end timestamp for overall processing
    overall_end_time = datetime.now()

    # Calculate overall duration
    overall_duration = (overall_end_time - overall_start_time).total_seconds()
    print(f"\nOverall Duration: {overall_duration} seconds\n")

    return results

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("index.html", error="No file part")

        file = request.files["file"]

        if file.filename == "":
            return render_template("index.html", error="No selected file")

        if file:
            filename = file.filename
            file_path = os.path.join("static/uploads", filename)
            file.save(file_path)

            results = process_images_in_folder("static/uploads")
            result = next((r for r in results if r["filename"] == filename), None)
            return render_template("result.html", result=result, results=results)

    return render_template("index.html", error=None)

@app.route("/show_all_results", methods=["GET"])
def show_all_results():
    # Retrieve all results for previously uploaded images
    results = process_images_in_folder("static/uploads")
    return render_template("index.html", error=None, results=results)

if __name__ == "__main__":
    os.makedirs("static/uploads", exist_ok=True)
    os.makedirs("static/resized", exist_ok=True)
    app.run(debug=True)
