import os
import logging
from flask import Flask, render_template, request, jsonify, send_file
from scraper import ImageScraper, FilterRule
import zipfile
from io import BytesIO
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Directory for storing scraped images
STATIC_DIR = os.path.join('static', 'scraped_images')
os.makedirs(STATIC_DIR, exist_ok=True)

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index page: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        url = request.form['url']
        folder_name = request.form['folder_name']

        # Create folder for this scraping session
        session_dir = os.path.join(STATIC_DIR, folder_name)
        os.makedirs(session_dir, exist_ok=True)

        # Process custom filter rules
        custom_rule = None
        include_terms = request.form.getlist('include_terms[]')
        exclude_terms = request.form.getlist('exclude_terms[]')
        min_width = int(request.form.get('min_width', 100))
        min_height = int(request.form.get('min_height', 100))

        if any([include_terms, exclude_terms]) or min_width != 100 or min_height != 100:
            custom_rule = FilterRule(
                include_terms=include_terms,
                exclude_terms=exclude_terms,
                min_width=min_width,
                min_height=min_height
            )

        # Initialize scraper
        scraper = ImageScraper()
        images = scraper.scrape(url, session_dir, custom_rule)

        if not images:
            return jsonify({
                'error': 'No suitable images found'
            }), 404

        # Convert file paths to URLs
        image_data = []
        seen_paths = set()
        for img_path in images:
            base_name = os.path.basename(img_path)
            if base_name not in seen_paths:
                with Image.open(img_path) as img:
                    width, height = img.size
                    image_data.append({
                        'url': f"/static/scraped_images/{folder_name}/{base_name}",
                        'width': width,
                        'height': height
                    })
                    seen_paths.add(base_name)

        return jsonify({
            'success': True,
            'message': f'Found {len(images)} images',
            'images': image_data,
            'folder_name': folder_name
        })

    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500, {'Content-Type': 'application/json'}

@app.route('/download/<folder_name>', methods=['GET'])
def download_zip(folder_name):
    try:
        # Create a BytesIO object to store the zip file
        memory_file = BytesIO()

        # Create the zip file
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Path to the folder containing images
            folder_path = os.path.join(STATIC_DIR, folder_name)

            # Add each file in the directory to the zip
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                # Add file to zip with just the filename (not full path)
                zf.write(file_path, filename)

        # Seek to the beginning of the BytesIO object
        memory_file.seek(0)

        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{folder_name}_banners.zip'
        )

    except Exception as e:
        logger.error(f"Error creating zip file: {str(e)}")
        return jsonify({'error': 'Failed to create zip file', 'status': 'error'}), 500, {'Content-Type': 'application/json'}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)