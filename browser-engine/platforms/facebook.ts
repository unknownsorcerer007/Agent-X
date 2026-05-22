/**
 * platforms/facebook.ts — Facebook-specific API adapter
 * Uses Facebook's Graph API for posting and media uploads
 */

import type { CDPSession, Page } from "playwright";

interface FacebookUploadResult {
  uploadId: string;
  status: string;
}

interface FacebookPostResult {
  postId: string;
  status: string;
}

interface FacebookProfile {
  id?: string;
  username?: string;
  name?: string;
  biography?: string;
  profilePicUrl?: string;
  coverUrl?: string;
  link?: string;
}

/**
 * Get Facebook access token from cookies or page data
 */
async function getAccessToken(page: Page): Promise<string> {
  // Try to extract from page context
  const token = await page.evaluate(() => {
    // Check window.__accessToken
    const win = window as any;
    if (win.__accessToken) return win.__accessToken;

    // Check for EAAB token pattern in page scripts
    const scripts = document.querySelectorAll("script");
    for (const script of scripts) {
      const text = script.textContent || "";
      const match = text.match(/"accessToken":"(EAAB[^"]+)"/);
      if (match) return match[1];
    }

    // Check for access token in localStorage
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key) {
          const val = localStorage.getItem(key);
          if (val && val.includes("EAAB")) {
            const match = val.match(/(EAAB[^"\\]+)/);
            if (match) return match[1];
          }
        }
      }
    } catch (e) {
      console.warn("[facebook] Failed to scan localStorage for access token:", e);
    }

    return "";
  });

  return token;
}

/**
 * Get Facebook user ID from cookies
 */
async function getUserId(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const cUser = cookies.find((c) => c.name === "c_user");
  return cUser?.value || "";
}

/**
 * Upload media to Facebook
 */
export async function uploadMedia(
  page: Page,
  cdpSession: CDPSession,
  filePath: string
): Promise<FacebookUploadResult> {
  const fs = await import("fs");
  const fileBuffer = fs.readFileSync(filePath);
  const accessToken = await getAccessToken(page);
  const userId = await getUserId(page);

  if (!accessToken) {
    throw new Error("No Facebook access token found. User may not be logged in.");
  }

  const base64Data = fileBuffer.toString("base64");

  // Upload via Graph API
  const result = await page.evaluate(
    async ({ accessToken, userId, base64Data }) => {
      const binaryData = Uint8Array.from(atob(base64Data), (c) => c.charCodeAt(0));
      const formData = new FormData();
      formData.append("source", new Blob([binaryData], { type: "image/jpeg" }), "photo.jpg");
      formData.append("published", "false");

      const endpoint = userId
        ? `https://graph.facebook.com/v18.0/${userId}/photos`
        : "https://graph.facebook.com/v18.0/me/photos";

      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        body: formData,
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    { accessToken, userId, base64Data }
  );

  if (result.status !== 200) {
    throw new Error(`Facebook upload failed: ${JSON.stringify(result.data)}`);
  }

  return {
    uploadId: result.data.id,
    status: "ok",
  };
}

/**
 * Create a post on Facebook
 */
export async function createPost(
  page: Page,
  cdpSession: CDPSession,
  caption: string,
  uploadId?: string,
  mediaType?: string,
  hashtags?: string[],
  location?: string
): Promise<FacebookPostResult> {
  const accessToken = await getAccessToken(page);
  const userId = await getUserId(page);

  if (!accessToken) {
    throw new Error("No Facebook access token found. User may not be logged in.");
  }

  let fullCaption = caption;
  if (hashtags && hashtags.length > 0) {
    fullCaption += "\n" + hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ");
  }

  const postData: any = {
    message: fullCaption,
  };

  if (uploadId) {
    // If we have a photo ID, attach it
    postData.attached_media = JSON.stringify([{ media_fbid: uploadId }]);
  }

  if (location) {
    postData.place = location;
  }

  const endpoint = userId
    ? `https://graph.facebook.com/v18.0/${userId}/feed`
    : "https://graph.facebook.com/v18.0/me/feed";

  const result = await page.evaluate(
    async ({ endpoint, postData, accessToken }) => {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(postData)) {
        params.append(key, String(value));
      }

      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Authorization: `Bearer ${accessToken}`,
        },
        body: params.toString(),
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    { endpoint, postData, accessToken }
  );

  if (result.status !== 200) {
    throw new Error(`Facebook create post failed: ${JSON.stringify(result.data)}`);
  }

  const postId = result.data.id;

  if (!postId) {
    throw new Error(`Facebook create post succeeded but no post ID returned in response: ${JSON.stringify(result.data)}`);
  }

  return {
    postId,
    status: "ok",
  };
}

/**
 * Delete a post on Facebook
 */
export async function deletePost(
  page: Page,
  cdpSession: CDPSession,
  postId: string
): Promise<{ status: string; message?: string }> {
  const accessToken = await getAccessToken(page);

  const result = await page.evaluate(
    async ({ postId, accessToken }) => {
      const response = await fetch(`https://graph.facebook.com/v18.0/${postId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      const data = await response.json().catch(() => null);
      return { status: response.status, data };
    },
    { postId, accessToken }
  );

  if (result.status !== 200 && result.status !== 204) {
    return { status: "error", message: `Facebook delete failed (HTTP ${result.status}): ${JSON.stringify(result.data)}` };
  }

  return { status: "ok" };
}

/**
 * Get profile info
 */
export async function getProfile(
  page: Page,
  cdpSession: CDPSession,
  username?: string
): Promise<FacebookProfile> {
  const accessToken = await getAccessToken(page);
  const userId = await getUserId(page);

  if (!accessToken) {
    return { error: "Not logged in" } as any;
  }

  const targetId = username || userId || "me";

  const result = await page.evaluate(
    async ({ targetId, accessToken }) => {
      const fields = "id,name,username,about,birthday,email,gender,hometown,link,location,quotes,relationship_status,website,cover,picture.width(200).height(200)";
      const response = await fetch(
        `https://graph.facebook.com/v18.0/${targetId}?fields=${fields}`,
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }
      );
      return await response.json();
    },
    { targetId, accessToken }
  );

  return {
    id: result.id,
    username: result.username,
    name: result.name,
    biography: result.about || result.quotes || "",
    profilePicUrl: result.picture?.data?.url || "",
    coverUrl: result.cover?.source || "",
    link: result.link || "",
  };
}

/**
 * Check if user is logged into Facebook
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
  const cookies = await page.context().cookies();
  const hasCUser = cookies.some((c) => c.name === "c_user");
  const hasFr = cookies.some((c) => c.name === "fr");
  const hasSb = cookies.some((c) => c.name === "sb");
  return hasCUser && (hasFr || hasSb);
}
