// This file contains JavaScript for the user-facing pages, handling form submissions and any client-side validation.

document.addEventListener('DOMContentLoaded', function() {
    const complaintForm = document.getElementById('complaintForm');

    if (complaintForm) {
        complaintForm.addEventListener('submit', function(event) {
            const email = document.getElementById('email').value;
            const prnOrFacultyId = document.getElementById('prnOrFacultyId').value;
            const category = document.getElementById('category').value;
            const description = document.getElementById('description').value;

            if (!email || !prnOrFacultyId || !category || !description) {
                event.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    }
});