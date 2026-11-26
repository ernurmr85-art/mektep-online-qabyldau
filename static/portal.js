
"use strict";

const labels = {
  student_name: "Оқушының аты-жөні",
  iin: "ЖСН",
  parent_name: "Ата-ананың аты-жөні",
  phone: "Телефон",
  address: "Мекенжай",
  full_name: "Аты-жөні",
  email: "Электрондық пошта",
  password: "Құпиясөз",
  title: "Бағыт атауы",
  grade: "Сынып",
  language: "Оқыту тілі",
  opens_on: "Басталу күні",
  closes_on: "Аяқталу күні",
  status: "Шешім",
  capacity: "Орын саны",
  document: "Құжат түрі",
  file: "Файл",
};

function validationMessage(detail) {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "Сұранысты орындау мүмкін болмады.";
  return detail.map(({loc, msg}) => {
    const field = loc.at(-1);
    if (field === "iin") return "ЖСН дәл 12 цифрдан тұруы керек.";
    if (field === "phone") return "Телефон нөмірінің пішімін тексеріңіз.";
    if (labels[field]) return labels[field] + " өрісін тексеріңіз.";
    return msg.replace(/^Value error, /, "");
  }).join(" ");
}

function jsonFields(form) {
  const fields = {};
  for (const field of form.querySelectorAll("input[name], select[name], textarea[name]")) {
    if (field.disabled) continue;
    if (field.type === "checkbox") fields[field.name] = field.checked;
    else if (field.type === "number" || field.hasAttribute("data-number")) {
      fields[field.name] = field.hasAttribute("data-nullable") && !field.value ? null : Number(field.value);
    }
    else fields[field.name] = field.value;
  }
  return fields;
}

document.querySelectorAll("form[data-api]").forEach((form) => {
  const output = form.querySelector(".form-message");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    output.textContent = "";
    const related = form.dataset.checkForm && document.getElementById(form.dataset.checkForm);
    if (related && [...related.elements].some((field) =>
      field instanceof HTMLInputElement && field.value !== field.defaultValue)) {
      output.textContent = "Алдымен енгізілген өзгерістерді сақтаңыз.";
      return;
    }
    const upload = form.dataset.checkUpload && document.getElementById(form.dataset.checkUpload);
    if (upload && upload.elements.file.files.length) {
      output.textContent = "Алдымен таңдалған құжатты жүктеңіз.";
      return;
    }
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;

    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    const headers = {"X-Mektep-Portal": "1"};
    const method = form.dataset.method || "POST";
    let body;
    if (form.dataset.encoding === "form") {
      body = new URLSearchParams(new FormData(form));
    } else if (form.dataset.encoding === "multipart") {
      body = new FormData(form);
    } else if (method !== "DELETE" && form.querySelector("[name]")) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(jsonFields(form));
    }

    try {
      const response = await fetch(form.dataset.api, {method, body, headers});
      const result = response.status === 204 ? null : await response.json();
      if (!response.ok) {
        output.textContent = validationMessage(result?.detail);
        const first = Array.isArray(result?.detail) && result.detail[0]?.loc?.at(-1);
        if (typeof first === "string") form.elements.namedItem(first)?.focus();
        return;
      }
      const target = new URL(form.dataset.next.replace("{id}", result?.id ?? ""), window.location.href);
      if (target.pathname === location.pathname && target.search === location.search && target.hash) {
        history.replaceState(null, "", target);
        window.location.reload();
      } else {
        window.location.assign(target);
      }
    } catch {
      output.textContent = "Серверге қосылу мүмкін болмады. Қайта көріңіз.";
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll("[data-decision]").forEach((select) => {
  select.addEventListener("change", () => {
    select.form.elements.note.required = ["rejected", "revision"].includes(select.value);
  });
});
