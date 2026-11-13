AOS.init({ duration: 800, once: true });

const form = document.getElementById("registrationForm");
const loadingOverlay = document.getElementById("loadingOverlay");

const showLoading = () => {
  if (loadingOverlay) {
    loadingOverlay.classList.remove("d-none");
  }
};

const hideLoading = () => {
  if (loadingOverlay) {
    loadingOverlay.classList.add("d-none");
  }
};

if (form) {
  form.addEventListener("submit", function (event) {
    const fields = [
      { id: "studentName" },
      { id: "parentName" },
      { id: "phone" },
      { id: "email" },
      { id: "classLevel" },
      { id: "schoolName" },
      { id: "address" },
    ];

    let isValid = true;
    fields.forEach(({ id }) => {
      const el = document.getElementById(id);
      el.classList.remove("is-invalid");
      if (!el || !el.value.trim()) {
        if (el) el.classList.add("is-invalid");
        isValid = false;
      }
    });

    const phone = document.getElementById("phone")?.value.trim();
    if (phone && !/^\d{10}$/.test(phone)) {
      document.getElementById("phone").classList.add("is-invalid");
      isValid = false;
    }

    const email = document.getElementById("email")?.value.trim();
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      document.getElementById("email").classList.add("is-invalid");
      isValid = false;
    }

    if (!isValid) {
      event.preventDefault();
      return;
    }

    showLoading();
  });
}

window.addEventListener("DOMContentLoaded", () => {
  const toastElements = document.querySelectorAll(".toast");
  toastElements.forEach((toastEl) => {
    const toast = new bootstrap.Toast(toastEl);
    toast.show();
  });

  if (toastElements.length > 0) {
    setTimeout(() => {
      hideLoading();
    }, 500);
  }
});
