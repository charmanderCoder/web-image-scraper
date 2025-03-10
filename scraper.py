import os
import logging
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image
import io
from requests.exceptions import RequestException, Timeout, ConnectionError

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ScraperError(Exception):
    """Base exception for scraper errors"""
    pass

class NetworkError(ScraperError):
    """Raised when network-related errors occur"""
    pass

class ImageProcessingError(ScraperError):
    """Raised when image processing fails"""
    pass

class FilterRule:
    def __init__(self, include_terms=None, exclude_terms=None, min_width=100, min_height=100, media_types=None):
        self.include_terms = [term.lower().strip() for term in (include_terms or [])]
        self.exclude_terms = [term.lower().strip() for term in (exclude_terms or [])]
        self.min_width = min_width
        self.min_height = min_height
        self.media_types = media_types or ['jpg', 'jpeg', 'png', 'gif']

        # Default marketing terms that should always be checked
        self.default_terms = [
            'banner', 'hero', 'slider', 'carousel', 'featured',
            'header', 'promotion', 'campaign', 'slide', 'image',
            'main-banner', 'homepage-banner', 'site-banner',
            'hero-banner', 'hero-image', 'hero-section',
            'media', 'media-image', 'media-content'
        ]

    def _extract_all_attributes(self, img_tag):
        """Extract all relevant attributes from the image and its parent elements"""
        try:
            all_attributes = set()
            current = img_tag
            depth = 0

            while current and depth < 5:
                # Add tag name
                all_attributes.add(current.name.lower())

                # Handle classes
                if current.get('class'):
                    # Add the full class string first (preserve exact matches)
                    if isinstance(current.get('class'), list):
                        full_class = ' '.join(current.get('class')).lower()
                    else:
                        full_class = current.get('class').lower()
                    all_attributes.add(full_class)

                    # Add individual classes
                    classes = full_class.split()
                    all_attributes.update(classes)

                # Add other attributes
                for attr in ['id', 'name', 'role', 'data-type', 'data-section-type']:
                    if current.get(attr):
                        all_attributes.add(current[attr].lower())

                # Move to parent
                current = current.parent
                depth += 1

            return all_attributes
        except Exception as e:
            logger.error(f"Error extracting attributes: {str(e)}")
            raise ScraperError(f"Failed to extract attributes: {str(e)}")

    def matches(self, img_tag, dimensions, all_attributes=None):
        """Check if an image matches the filtering rules"""
        try:
            width, height = dimensions

            # Skip tiny images
            if width < self.min_width or height < self.min_height:
                return False, []

            # If no include terms and no exclude terms are set, accept all images
            if not self.include_terms and not self.exclude_terms:
                # Still return a default term for consistency
                return True, ['unfiltered']

            # Extract all attributes from image and parents if not provided
            if all_attributes is None:
                all_attributes = self._extract_all_attributes(img_tag)

            # Debug logging
            logger.debug(f"Checking image with attributes: {all_attributes}")
            logger.debug(f"Include terms: {self.include_terms}")

            # Check exclude terms first
            if self.exclude_terms:
                for term in self.exclude_terms:
                    if self._term_matches(term, all_attributes):
                        logger.debug(f"Excluded by term: {term}")
                        return False, []

            # Check custom include terms
            matched_terms = []
            if self.include_terms:
                for term in self.include_terms:
                    if self._term_matches(term, all_attributes):
                        logger.debug(f"Matched include term: {term}")
                        matched_terms.append(term)

            # If no custom terms matched or no custom terms provided, check default terms
            if not matched_terms and self.include_terms:  # Only check default terms if include_terms were specified
                for term in self.default_terms:
                    if self._term_matches(term, all_attributes):
                        logger.debug(f"Matched default term: {term}")
                        matched_terms.append(term)

            # Accept if any terms matched or if no filters are set
            return bool(matched_terms) or not self.include_terms, matched_terms or ['unfiltered']

        except Exception as e:
            logger.error(f"Error in filter matching: {str(e)}")
            raise ScraperError(f"Failed to apply filters: {str(e)}")

    def _term_matches(self, term, all_attributes):
        """Check if a term matches any attribute"""
        try:
            term = term.lower().strip()

            # First try exact match
            if term in all_attributes:
                logger.debug(f"Exact match found for term: {term}")
                return True

            # If no exact match, try matching individual parts
            term_parts = term.split()
            for attr in all_attributes:
                # For compound terms, all parts must match
                if len(term_parts) > 1:
                    attr_parts = attr.split()
                    if all(tp in attr_parts for tp in term_parts):
                        logger.debug(f"Compound match found for term: {term} in attribute: {attr}")
                        return True

            return False
        except Exception as e:
            logger.error(f"Error matching terms: {str(e)}")
            raise ScraperError(f"Failed to match terms: {str(e)}")

class ImageScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
        self.allowed_formats = ['jpg', 'jpeg', 'png', 'gif', 'webp']
        self.minimal_size = 10  # Minimal size in pixels when no filters are applied

    def get_image_url(self, img_tag):
        """Extract highest quality image URL from various tag attributes"""
        def parse_srcset(srcset_str):
            """Parse srcset string and return the highest quality image URL"""
            try:
                best_url = None
                max_width = 0
                max_pixel_ratio = 0

                for srcset_item in srcset_str.split(','):
                    parts = srcset_item.strip().split()
                    if len(parts) >= 2:
                        url = parts[0]
                        descriptor = parts[1]

                        # Handle width descriptors (e.g., 800w)
                        if descriptor.endswith('w'):
                            try:
                                width = int(descriptor[:-1])
                                if width > max_width:
                                    max_width = width
                                    best_url = url
                            except ValueError:
                                continue

                        # Handle pixel density descriptors (e.g., 2x)
                        elif descriptor.endswith('x'):
                            try:
                                ratio = float(descriptor[:-1])
                                if ratio > max_pixel_ratio:
                                    max_pixel_ratio = ratio
                                    best_url = url
                            except ValueError:
                                continue

                # Prefer width-based URLs over pixel ratio-based ones
                return best_url
            except Exception as e:
                logger.warning(f"Error parsing srcset: {str(e)}")
                return None

        # Try different attributes where image URL might be stored
        for attr in ['srcset', 'data-srcset', 'src', 'data-src', 'data-original', 'data-lazy-src']:
            url = img_tag.get(attr, '')
            if url:
                # Handle srcset attributes
                if 'srcset' in attr:
                    high_quality_url = parse_srcset(url)
                    if high_quality_url:
                        return high_quality_url.strip()
                else:
                    # For regular URLs, check if it's a small preview (contains dimensions)
                    if any(x in url.lower() for x in ['_100x', '_thumb', '_small', '_mini']):
                        # Try to find a srcset with better quality
                        for srcset_attr in ['srcset', 'data-srcset']:
                            srcset = img_tag.get(srcset_attr)
                            if srcset:
                                high_quality_url = parse_srcset(srcset)
                                if high_quality_url:
                                    return high_quality_url.strip()
                    return url.strip()

        # Check parent picture element for source tags
        if img_tag.parent and img_tag.parent.name == 'picture':
            best_source_url = None
            max_width = 0

            for source in img_tag.parent.find_all('source'):
                # Check srcset in source tags
                srcset = source.get('srcset', '')
                if srcset:
                    url = parse_srcset(srcset)
                    if url:
                        # Try to get width from media query
                        media = source.get('media', '')
                        if 'min-width' in media:
                            try:
                                width = int(''.join(filter(str.isdigit, media)))
                                if width > max_width:
                                    max_width = width
                                    best_source_url = url
                            except ValueError:
                                if not best_source_url:
                                    best_source_url = url
                        else:
                            if not best_source_url:
                                best_source_url = url

            if best_source_url:
                return best_source_url.strip()

        return None

    def fix_url(self, url, base_url):
        """Fix protocol-relative URLs and make relative URLs absolute"""
        try:
            if not url:
                return None

            # Handle protocol-relative URLs
            if url.startswith('//'):
                parsed_base = urlparse(base_url)
                return f"{parsed_base.scheme}:{url}"

            # Handle data URLs
            if url.startswith('data:'):
                return None

            return urljoin(base_url, url)
        except Exception as e:
            logger.error(f"Error fixing URL: {str(e)}")
            raise NetworkError(f"Invalid URL format: {str(e)}")

    def get_image_dimensions(self, content):
        """Get image dimensions from content"""
        try:
            img = Image.open(io.BytesIO(content))
            return img.size
        except Exception as e:
            logger.error(f"Error getting image dimensions: {str(e)}")
            raise ImageProcessingError(f"Failed to process image: {str(e)}")

    def scrape(self, url, output_dir, custom_rule=None):
        """Scrape images from URL"""
        images = []
        image_info = []
        try:
            # Fetch the webpage
            logger.info(f"Scraping URL: {url}")
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
            except Timeout:
                raise NetworkError("Request timed out. The website might be slow or unavailable")
            except ConnectionError:
                raise NetworkError("Failed to connect to the website. Please check the URL and try again")
            except RequestException as e:
                raise NetworkError(f"Failed to fetch the webpage: {str(e)}")

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all image tags and source tags (for picture elements)
            img_tags = soup.find_all(['img', 'picture'])
            if not img_tags:
                raise ScraperError("No image tags found on the page")

            logger.info(f"Found {len(img_tags)} total image tags")

            # Use custom rule if provided, otherwise use default
            rule = custom_rule or FilterRule()

            for i, img in enumerate(img_tags):
                try:
                    # Get image source from various possible attributes
                    src = self.get_image_url(img)
                    if not src:
                        continue

                    # Fix and make URL absolute
                    src = self.fix_url(src, url)
                    if not src:
                        continue

                    logger.debug(f"Processing image {i}: {src}")

                    # Download image
                    try:
                        img_response = requests.get(src, headers=self.headers, timeout=10)
                        img_response.raise_for_status()
                    except Exception as e:
                        logger.warning(f"Failed to download image {src}: {str(e)}")
                        continue

                    content = img_response.content
                    try:
                        dimensions = self.get_image_dimensions(content)
                    except ImageProcessingError:
                        logger.warning(f"Failed to process image {src}")
                        continue

                    # Skip images smaller than minimal size when no filters
                    if not rule.include_terms and not rule.exclude_terms:
                        if dimensions[0] < self.minimal_size or dimensions[1] < self.minimal_size:
                            continue

                    # Get image format and save
                    img = Image.open(io.BytesIO(content))
                    img_format = img.format.lower() if img.format else 'jpg'

                    # Skip unsupported formats
                    if img_format not in self.allowed_formats:
                        continue

                    # Apply filtering rules if they exist
                    if rule.include_terms or rule.exclude_terms:
                        all_attributes = self._extract_all_attributes(img)
                        matches, matched_terms = rule.matches(img, dimensions, all_attributes)
                        if not matches:
                            continue
                    else:
                        matched_terms = ['unfiltered']

                    image_path = os.path.join(output_dir, f"image_{len(images)}.{img_format}")
                    try:
                        with open(image_path, 'wb') as f:
                            f.write(content)
                    except IOError as e:
                        logger.error(f"Failed to save image: {str(e)}")
                        continue

                    images.append(image_path)
                    image_info.append({
                        'path': image_path,
                        'matched_terms': matched_terms,
                        'format': img_format,
                        'dimensions': dimensions
                    })
                    logger.info(f"Saved image: {image_path}")

                except Exception as e:
                    logger.error(f"Error processing image {i}: {str(e)}")
                    continue

            if not images:
                if rule.include_terms or rule.exclude_terms:
                    raise ScraperError("No images found that match your filter criteria. Try adjusting your filters.")
                else:
                    raise ScraperError("No accessible images found on the website.")

            logger.info(f"Successfully scraped {len(images)} images")
            return images, image_info

        except ScraperError as e:
            raise
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            raise ScraperError(f"Scraping failed: {str(e)}")