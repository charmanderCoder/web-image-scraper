import os
import logging
from flask import Flask, render_template, request, jsonify, send_file
from scraper import ImageScraper, FilterRule
import zipfile
from io import BytesIO
from PIL import Image
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Directory for storing scraped images
STATIC_DIR = os.path.join('static', 'scraped_images')
os.makedirs(STATIC_DIR, exist_ok=True)

def validate_url(url):
    """Validate URL format and scheme"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except Exception:
        return False

def validate_folder_name(name):
    """Validate folder name"""
    return name and all(c not in r'\/:*?"<>|' for c in name)

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
        # Validate inputs
        url = request.form.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        if not validate_url(url):
            return jsonify({'error': 'Invalid URL format. Please enter a valid HTTP/HTTPS URL'}), 400

        folder_name = request.form.get('folder_name')
        if not folder_name:
            return jsonify({'error': 'Folder name is required'}), 400
        if not validate_folder_name(folder_name):
            return jsonify({'error': 'Invalid folder name. Avoid special characters: \/:*?"<>|'}), 400

        # Create folder for this scraping session
        session_dir = os.path.join(STATIC_DIR, folder_name)
        try:
            os.makedirs(session_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory: {str(e)}")
            return jsonify({'error': 'Failed to create storage directory'}), 500

        # Check if filters are disabled
        disable_filters = request.form.get('disable_filters') == 'on'

        try:
            if not disable_filters:
                # Process filter options only if filters are not disabled
                include_terms = request.form.getlist('include_terms[]')
                exclude_terms = request.form.getlist('exclude_terms[]')
                try:
                    min_width = int(request.form.get('min_width', 100))
                    min_height = int(request.form.get('min_height', 100))
                except ValueError:
                    return jsonify({'error': 'Invalid dimensions. Width and height must be numbers'}), 400

                media_types = request.form.getlist('media_types[]') or ['jpg', 'jpeg', 'png', 'gif']

                custom_rule = None
                if any([include_terms, exclude_terms]) or min_width != 100 or min_height != 100:
                    custom_rule = FilterRule(
                        include_terms=include_terms,
                        exclude_terms=exclude_terms,
                        min_width=min_width,
                        min_height=min_height,
                        media_types=media_types
                    )
            else:
                # When filters are disabled, use a very permissive rule
                custom_rule = FilterRule(
                    include_terms=[],
                    exclude_terms=[],
                    min_width=1,
                    min_height=1,
                    media_types=['jpg', 'jpeg', 'png', 'gif', 'webp']
                )

            # Initialize scraper
            scraper = ImageScraper()
            images, image_info = scraper.scrape(url, session_dir, custom_rule)

            if not images:
                return jsonify({
                    'error': 'No images found. Try adjusting your filters or check if the website contains images'
                }), 404

            # Convert file paths to URLs and include matched terms
            image_data = []
            seen_paths = set()
            for info in image_info:
                base_name = os.path.basename(info['path'])
                if base_name not in seen_paths:
                    image_data.append({
                        'url': f"/static/scraped_images/{folder_name}/{base_name}",
                        'width': info['dimensions'][0],
                        'height': info['dimensions'][1],
                        'matched_terms': info['matched_terms'],
                        'format': info['format']
                    })
                    seen_paths.add(base_name)

            return jsonify({
                'success': True,
                'message': f'Successfully scraped {len(images)} images',
                'images': image_data,
                'folder_name': folder_name
            })

        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except ConnectionError as e:
            logger.error(f"Connection error: {str(e)}")
            return jsonify({'error': 'Failed to connect to the website. Please check the URL and try again'}), 503
        except TimeoutError as e:
            logger.error(f"Timeout error: {str(e)}")
            return jsonify({'error': 'Request timed out. The website might be slow or unavailable'}), 504
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return jsonify({'error': f'An error occurred while scraping: {str(e)}'}), 500

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/download/<folder_name>', methods=['GET'])
def download_zip(folder_name):
    try:
        if not validate_folder_name(folder_name):
            return jsonify({'error': 'Invalid folder name'}), 400

        folder_path = os.path.join(STATIC_DIR, folder_name)
        if not os.path.exists(folder_path):
            return jsonify({'error': 'Folder not found'}), 404

        memory_file = BytesIO()
        try:
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    if os.path.isfile(file_path):
                        zf.write(file_path, filename)
        except Exception as e:
            logger.error(f"Error creating zip file: {str(e)}")
            return jsonify({'error': 'Failed to create zip file'}), 500

        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{folder_name}_banners.zip'
        )

    except Exception as e:
        logger.error(f"Error in download: {str(e)}")
        return jsonify({'error': 'Failed to prepare download'}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)