document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const messageDiv = document.getElementById("message");
  const loginDialog = document.getElementById("login-dialog");
  const loginForm = document.getElementById("login-form");
  const loginError = document.getElementById("login-error");
  const loginButton = document.getElementById("login-button");
  const logoutButton = document.getElementById("logout-button");
  const accountButton = document.getElementById("account-button");
  const accountMenu = document.getElementById("account-menu");
  let token = null;
  let teacher = null;
  let activities = {};

  function showMessage(text, isError = false) {
    messageDiv.textContent = text;
    messageDiv.className = isError ? "message error" : "message success";
  }

  function updateAccount() {
    signupForm.classList.toggle("hidden", !token);
    document.getElementById("login-notice").classList.toggle("hidden", !!token);
    loginButton.classList.toggle("hidden", !!token);
    logoutButton.classList.toggle("hidden", !token);
    document.getElementById("account-label").textContent = teacher || "Teacher account";
    renderActivities();
  }

  async function api(path, options = {}) {
    const headers = { ...options.headers };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(path, { ...options, headers });
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401 && token) {
        token = null;
        teacher = null;
        updateAccount();
      }
      const detail = typeof result.detail === "string" ? result.detail : "Invalid request";
      throw new Error(detail);
    }
    return result;
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function actionButton(label, action, className) {
    const button = element("button", label, className);
    button.type = "button";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await action();
      } catch (error) {
        showMessage(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
    return button;
  }

  async function changeRegistration(name, email, action, decision) {
    const path = `/activities/${encodeURIComponent(name)}/${action}?email=${encodeURIComponent(email)}`;
    const options = decision
      ? {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        }
      : { method: "DELETE" };
    const result = await api(path, options);
    showMessage(result.message);
    await fetchActivities();
  }

  function renderActivities() {
    activitiesList.replaceChildren();
    const selected = activitySelect.value;
    activitySelect.replaceChildren(element("option", "-- Select an activity --"));
    activitySelect.firstElementChild.value = "";

    Object.entries(activities).forEach(([name, details]) => {
      const card = element("div", undefined, "activity-card");
      card.append(
        element("h4", name),
        element("p", details.description),
        element("p", `Schedule: ${details.schedule}`),
        element("p", `Availability: ${details.max_participants - details.participants.length} spots left`)
      );
      const participants = element("div", undefined, "participants-section participants-container");
      participants.append(element("h5", "Participants:"));
      const list = element("ul", undefined, "participants-list");
      details.participants.forEach((email) => {
        const row = element("li");
        row.append(element("span", email, "participant-email"));
        if (token) {
          const button = actionButton("Remove", () => changeRegistration(name, email, "unregister"), "delete-btn");
          button.setAttribute("aria-label", `Remove ${email} from ${name}`);
          row.append(button);
        }
        list.append(row);
      });
      participants.append(details.participants.length ? list : element("p", "No participants yet"));
      card.append(participants);

      if (token && details.pending_requests?.length) {
        const pending = element("div", undefined, "pending-requests");
        pending.append(element("h5", "Pending registration requests:"));
        const requests = element("ul");
        details.pending_requests.forEach((email) => {
          const row = element("li");
          row.append(element("span", email));
          ["approve", "reject"].forEach((decision) => {
            const button = actionButton(
              decision === "approve" ? "Approve" : "Reject",
              () => changeRegistration(name, email, "requests", decision)
            );
            button.setAttribute("aria-label", `${decision} ${email} for ${name}`);
            row.append(button);
          });
          requests.append(row);
        });
        pending.append(requests);
        card.append(pending);
      }
      activitiesList.append(card);
      const option = element("option", name);
      option.value = name;
      activitySelect.append(option);
    });
    activitySelect.value = selected;
  }

  async function fetchActivities() {
    activities = await api("/activities");
    renderActivities();
  }

  accountButton.addEventListener("click", () => {
    const hidden = accountMenu.classList.toggle("hidden");
    accountButton.setAttribute("aria-expanded", String(!hidden));
  });
  loginButton.addEventListener("click", () => {
    loginError.textContent = "";
    loginDialog.showModal();
  });
  document.getElementById("cancel-login").addEventListener("click", () => loginDialog.close());
  loginDialog.addEventListener("close", () => loginForm.reset());

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = loginForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    loginError.textContent = "";
    try {
      const result = await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("username").value,
          password: document.getElementById("password").value,
        }),
      });
      token = result.access_token;
      teacher = result.username;
      loginDialog.close();
      updateAccount();
      showMessage(`Logged in as ${teacher}`);
      await fetchActivities();
    } catch (error) {
      if (loginDialog.open) loginError.textContent = error.message;
      else showMessage(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  logoutButton.addEventListener("click", async () => {
    try {
      await api("/auth/logout", { method: "POST" });
      token = null;
      teacher = null;
      updateAccount();
      signupForm.reset();
      showMessage("Logged out");
    } catch (error) {
      showMessage(error.message, true);
    }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = signupForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      const email = document.getElementById("email").value;
      const activity = activitySelect.value;
      const result = await api(
        `/activities/${encodeURIComponent(activity)}/signup?email=${encodeURIComponent(email)}`,
        { method: "POST" }
      );
      showMessage(result.message);
      signupForm.reset();
      await fetchActivities();
    } catch (error) {
      showMessage(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  fetchActivities().catch((error) => {
    activitiesList.textContent = "Failed to load activities. Please try again later.";
    showMessage(error.message, true);
  });
});
