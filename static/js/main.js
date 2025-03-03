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
    const imagePreviewModal = new bootstrap.Modal(document.getElementById('imagePreviewModal'));
    const previewImage = document.getElementById('previewImage');

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
            formData.set('include_terms', includeTerms.split(',').map(term => term.trim()).filter(Boolean));
        }

        const excludeTerms = formData.get('exclude_terms');
        if (excludeTerms) {
            formData.set('exclude_terms', excludeTerms.split(',').map(term => term.trim()).filter(Boolean));
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

            // Show success message
            resultMessage.textContent = data.message;
            resultDiv.classList.remove('d-none');

            // Setup download button
            downloadBtn.onclick = () => {
                window.location.href = `/download/${data.folder_name}`;
            };

            // Display images in grid
            data.images.forEach((image, index) => {
                const col = document.createElement('div');
                col.className = 'col-md-6 col-lg-4';

                const card = document.createElement('div');
                card.className = 'card h-100';

                const imgWrapper = document.createElement('div');
                imgWrapper.className = 'card-img-wrapper';

                const isVideo = image.url.endsWith('.mp4');
                const mediaElem = document.createElement(isVideo ? 'video' : 'img');
                mediaElem.src = image.url;
                mediaElem.className = 'card-img-top';
                if (isVideo) {
                    mediaElem.controls = true;
                } else {
                    mediaElem.alt = `Scraped Banner ${index + 1}`;
                    mediaElem.onload = function() {
                        const aspectRatio = (this.naturalHeight / this.naturalWidth) * 100;
                        imgWrapper.style.paddingTop = `${aspectRatio}%`;
                    };
                }

                imgWrapper.appendChild(mediaElem);
                card.appendChild(imgWrapper);

                card.onclick = () => {
                    previewImage.innerHTML = '';
                    const previewElem = mediaElem.cloneNode(true);
                    previewImage.appendChild(previewElem);
                    imagePreviewModal.show();

                    // Setup single image download
                    const downloadBtn = document.getElementById('downloadSingleImage');
                    downloadBtn.onclick = () => {
                        fetch(image.url)
                            .then(res => res.blob())
                            .then(blob => {
                                const url = window.URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.style.display = 'none';
                                a.href = url;
                                a.download = image.url.split('/').pop();
                                document.body.appendChild(a);
                                a.click();
                                window.URL.revokeObjectURL(url);
                                document.body.removeChild(a);
                            });
                    };
                };

                const cardBody = document.createElement('div');
                cardBody.className = 'card-body text-center';

                const dimensions = document.createElement('div');
                dimensions.className = 'image-dimensions';
                dimensions.textContent = `${image.width || '?'}×${image.height || '?'} px`;

                cardBody.appendChild(dimensions);
                card.appendChild(cardBody);
                col.appendChild(card);
                imageGrid.appendChild(col);
            });

        } catch (error) {
            // Show error message
            errorMessage.textContent = error.message;
            errorDiv.classList.remove('d-none');
        } finally {
            // Reset button state
            spinner.classList.add('d-none');
            btnText.textContent = 'Start Scraping';
            scrapeBtn.disabled = false;
        }
    });
});