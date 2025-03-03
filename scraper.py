import os
import logging
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image
import io

logger = logging.getLogger(__name__)

class FilterRule:
    def __init__(self, include_terms=None, exclude_terms=None, min_width=100, min_height=100):
        self.include_terms = [term.lower().strip() for term in (include_terms or [])]
        self.exclude_terms = [term.lower().strip() for term in (exclude_terms or [])]
        self.min_width = min_width
        self.min_height = min_height

    def _term_matches(self, term, attributes):
        """Check if a term matches any part of the attributes"""
        # Split attributes into words to avoid partial matches
        words = set(attributes.lower().split())
        return any(
            # Check exact word matches
            term == word or
            # Check compound terms (e.g., "banner-image")
            term in word.split('-') or
            # Check compound terms with underscore
            term in word.split('_')
            for word in words
        )

    def matches(self, img_tag, dimensions, all_attributes):
        """Check if an image matches this rule"""
        width, height = dimensions

        # Check minimum dimensions
        if width < self.min_width or height < self.min_height:
            logger.debug(f"Image too small: {width}x{height}")
            return False

        # First check exclude terms - if any match, reject immediately
        if self.exclude_terms:
            for term in self.exclude_terms:
                if self._term_matches(term, all_attributes):
                    logger.debug(f"Excluding due to term '{term}' found in: {all_attributes}")
                    return False

        # Then check include terms if specified
        if self.include_terms:
            has_include_term = False
            for term in self.include_terms:
                if self._term_matches(term, all_attributes):
                    has_include_term = True
                    logger.debug(f"Including due to term '{term}' found in: {all_attributes}")
                    break
            if not has_include_term:
                logger.debug(f"No include terms found in: {all_attributes}")
                return False

        return True

class ImageScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.allowed_formats = ['jpg', 'jpeg', 'png']
        # Default filter rule
        self.default_rule = FilterRule(
            include_terms=[
                'banner', 'hero', 'slider', 'carousel', 'featured',
                'header', 'promotion', 'campaign', 'slide', 'image',
                'img-box', 'main', 'content', 'full-width', 'one_image',
                'logolist', 'img-box', 'image-box', 'one-image', 'logo-list''images-contain', 'image-contain', 'image-contain-box', 'image-contain-box','adaptive_height slide-mobile','item slick-slide','item slick-slide slick-current slick-active','slick-track','slick-list draggable','item slick-slide','shopify-section home-slideshow-sections','slideshow slick-initialized slick-slider slick-dotted','slick-list draggable','container-fluid','hero__content__wrapper','column__media','carousel-slide s__block s__block--columnImage'
            ],
            exclude_terms=[
                'desktop-only', 'desktop-banner',
                'desktop-view', 'desktop-version',
                'thumbnail', 'mini-thumb', 'cart',
                'wishlist', 'avatar', 'icon', "product-grid-item", "product-card-wrapper", "product-card","product-card-image","product-card-image-wrapper","product-card-image-wrapper-inner","card-image-wrapper","card-image-wrapper-inner","card-image","card-image-inner",
            ],
            min_width=100,
            min_height=100
        )

    def fix_url(self, url, base_url):
        """Fix protocol-relative URLs and make relative URLs absolute"""
        if url.startswith('//'):
            parsed_base = urlparse(base_url)
            return f"{parsed_base.scheme}:{url}"
        return urljoin(base_url, url)

    def is_likely_banner(self, img_tag, dimensions, custom_rule=None):
        """Determine if an image is likely to be a banner"""
        rule = custom_rule or self.default_rule

        # Get all relevant attributes
        img_class = ' '.join(img_tag.get('class', [])).lower()
        img_id = img_tag.get('id', '').lower()
        img_alt = img_tag.get('alt', '').lower()
        img_src = img_tag.get('src', '').lower()
        img_title = img_tag.get('title', '').lower()

        # Combine all attributes for searching
        all_attributes = f"{img_class} {img_id} {img_alt} {img_src} {img_title}"

        # Add parent attributes
        parent_elements = img_tag.find_parents(['div', 'section', 'article', 'picture', 'a'])
        for parent in parent_elements:
            parent_class = ' '.join(parent.get('class', [])).lower()
            parent_id = parent.get('id', '').lower()
            all_attributes += f" {parent_class} {parent_id}"

        return rule.matches(img_tag, dimensions, all_attributes)

    def get_image_dimensions(self, content):
        """Get image dimensions from content"""
        try:
            img = Image.open(io.BytesIO(content))
            return img.size
        except Exception as e:
            logger.error(f"Error getting image dimensions: {str(e)}")
            return (0, 0)

    def scrape(self, url, output_dir, custom_rule=None):
        """Scrape images from URL"""
        images = []
        try:
            # Fetch the webpage
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all image tags
            img_tags = soup.find_all('img')
            logger.debug(f"Found {len(img_tags)} total images")

            for i, img in enumerate(img_tags):
                try:
                    # Get image source
                    src = img.get('src')
                    if not src or src.startswith('data:'):
                        continue

                    # Fix and make URL absolute
                    src = self.fix_url(src, url)
                    logger.debug(f"Processing image {i}: {src}")

                    # Download image
                    img_response = requests.get(src, headers=self.headers)
                    if not img_response.ok:
                        logger.warning(f"Failed to download image: {src}")
                        continue

                    content = img_response.content

                    # Check dimensions before processing further
                    dimensions = self.get_image_dimensions(content)
                    logger.debug(f"Image dimensions: {dimensions}")

                    # Skip if not a likely banner
                    if not self.is_likely_banner(img, dimensions, custom_rule):
                        continue

                    # Determine image format
                    img = Image.open(io.BytesIO(content))
                    img_format = img.format.lower() if img.format else 'jpg'

                    # Save image
                    image_path = os.path.join(output_dir, f"banner_{len(images)}.{img_format}")
                    with open(image_path, 'wb') as f:
                        f.write(content)

                    images.append(image_path)
                    logger.debug(f"Saved banner image: {image_path}")

                except Exception as e:
                    logger.error(f"Error processing image {i}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            raise

        return images