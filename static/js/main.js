document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('scrapeForm');
    const scrapeBtn = document.getElementById('scrapeBtn');
    const spinner = scrapeBtn.querySelector('.spinner-border');
    const btnText = scrapeBtn.querySelector('.btn-text');
    const resultDiv = document.getElementById('result');
    const errorDiv = document.getElementById('error');
    const resultMessage = document.getElementById('resultMessage');
    const errorMessage = document.getElementById('errorMessage');
    const imageGrid = document.getElementById('imageGrid');
    const downloadBtn = document.getElementById('downloadBtn');
    let allScrapedResults = []; // Store all results

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Form validation
        if (!form.checkValidity()) {
            e.stopPropagation();
            form.classList.add('was-validated');
            return;
        }

        // Reset UI
        resultDiv.classList.add('d-none');
        errorDiv.classList.add('d-none');
        imageGrid.innerHTML = '';
        spinner.classList.remove('d-none');
        btnText.textContent = 'Scraping...';
        scrapeBtn.disabled = true;

        const formData = new FormData(form);

        // Process filter terms
        const includeTerms = formData.get('include_terms');
        if (includeTerms) {
            const terms = includeTerms.match(/(?:[^,"]|"(?:\\.|[^"])*")+/g) || [];
            formData.delete('include_terms');
            terms.forEach(term => {
                term = term.replace(/^"(.*)"$/, '$1').trim();
                if (term) {
                    formData.append('include_terms[]', term);
                }
            });
        }

        const excludeTerms = formData.get('exclude_terms');
        if (excludeTerms) {
            const terms = excludeTerms.match(/(?:[^,"]|"(?:\\.|[^"])*")+/g) || [];
            formData.delete('exclude_terms');
            terms.forEach(term => {
                term = term.replace(/^"(.*)"$/, '$1').trim();
                if (term) {
                    formData.append('exclude_terms[]', term);
                }
            });
        }

        try {
            const response = await fetch('/scrape', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Scraping failed');
            }

            // Store all results
            allScrapedResults = data.images;

            // Show success message
            resultMessage.textContent = data.message;
            resultDiv.classList.remove('d-none');

            // Setup download button
            downloadBtn.onclick = () => {
                window.location.href = `/download/${data.folder_name}`;
            };

            // Display all images initially
            displayImages(allScrapedResults);

        } catch (error) {
            errorMessage.textContent = error.message;
            if (error.stack) {
                document.getElementById('errorDetails').textContent = error.stack;
            }
            errorDiv.classList.remove('d-none');
        } finally {
            spinner.classList.add('d-none');
            btnText.textContent = 'Start Scraping';
            scrapeBtn.disabled = false;
        }
    });

    // Media type filter handlers
    document.querySelectorAll('#mediaTypeFilters button').forEach(button => {
        button.addEventListener('click', function() {
            // Update active state
            document.querySelectorAll('#mediaTypeFilters button').forEach(btn => {
                btn.classList.remove('active');
            });
            this.classList.add('active');

            const mediaType = this.dataset.mediaType;
            let filteredResults = allScrapedResults;

            // Filter results based on media type
            if (mediaType !== 'all') {
                filteredResults = allScrapedResults.filter(image => {
                    if (mediaType === 'image') {
                        return ['jpg', 'jpeg', 'png'].includes(image.format.toLowerCase());
                    } else if (mediaType === 'gif') {
                        return image.format.toLowerCase() === 'gif';
                    } else if (mediaType === 'video') {
                        return ['mp4', 'webm'].includes(image.format.toLowerCase());
                    }
                    return true;
                });
            }

            // Display filtered results
            displayImages(filteredResults);
        });
    });

    function displayImages(images) {
        imageGrid.innerHTML = '';

        images.forEach((image, index) => {
            const col = document.createElement('div');
            col.className = 'col-md-6 col-lg-4';

            const card = document.createElement('div');
            card.className = 'card h-100';

            const imgWrapper = document.createElement('div');
            imgWrapper.className = 'card-img-wrapper';

            const isVideo = image.format === 'mp4' || image.format === 'webm';
            const mediaElem = document.createElement(isVideo ? 'video' : 'img');
            mediaElem.src = image.url;
            mediaElem.className = 'card-img-top';

            if (isVideo) {
                mediaElem.controls = true;
            } else {
                mediaElem.alt = `Scraped Media ${index + 1}`;
                mediaElem.onload = function() {
                    const aspectRatio = (this.naturalHeight / this.naturalWidth) * 100;
                    imgWrapper.style.paddingTop = `${aspectRatio}%`;
                };
            }

            imgWrapper.appendChild(mediaElem);
            card.appendChild(imgWrapper);

            const cardBody = document.createElement('div');
            cardBody.className = 'card-body';

            if (image.matched_terms && image.matched_terms.length > 0) {
                const matchedTerms = document.createElement('div');
                matchedTerms.className = 'matched-terms mb-2';
                matchedTerms.innerHTML = '<strong>Matched Terms:</strong><br>';
                image.matched_terms.forEach(term => {
                    const badge = document.createElement('span');
                    const isDefaultTerm = ['banner', 'hero', 'slider', 'carousel', 'featured',
                        'header', 'promotion', 'campaign', 'slide', 'image',
                        'main-banner', 'homepage-banner', 'site-banner',
                        'hero-banner', 'hero-image', 'hero-section',
                        'media', 'media-image', 'media-content'].includes(term.toLowerCase());
                    badge.className = `badge ${isDefaultTerm ? 'bg-info' : 'bg-success'} me-1 mb-1`;
                    badge.textContent = term;
                    matchedTerms.appendChild(badge);
                });
                cardBody.appendChild(matchedTerms);
            }

            const dimensions = document.createElement('div');
            dimensions.className = 'image-dimensions';
            dimensions.innerHTML = `<i class="fas fa-ruler me-1"></i>${image.width}×${image.height}px`;

            const format = document.createElement('div');
            format.className = 'image-format mt-1';
            format.innerHTML = `<i class="fas fa-file-image me-1"></i>${image.format.toUpperCase()}`;

            cardBody.appendChild(dimensions);
            cardBody.appendChild(format);
            card.appendChild(cardBody);
            col.appendChild(card);
            imageGrid.appendChild(col);
        });
    }
});