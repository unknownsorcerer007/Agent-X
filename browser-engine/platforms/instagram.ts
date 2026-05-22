/**
 * platforms/instagram.ts — Instagram-specific API adapter
 * Uses Instagram's native upload and configure APIs (not UI automation)
 * This is the method that actually works for posting — UI clicks get blocked.
 */

import type { CDPSession, Page } from "playwright";

const IG_APP_ID = process.env.IG_APP_ID || "936619743392459";
const IG_CREATE_POST_DOC_ID = process.env.IG_CREATE_POST_DOC_ID || "6511191288958346";

interface InstagramUploadResult {
  uploadId: string;
  status: string;
}

interface InstagramPostResult {
  mediaId: string;
  status: string;
}

interface InstagramProfile {
  username: string;
  fullName: string;
  biography: string;
  followerCount?: number;
  followingCount?: number;
  postCount?: number;
  isPrivate?: boolean;
  isVerified?: boolean;
  profilePicUrl: string;
}

/**
 * Get CSRF token from cookies
 */
async function getCsrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const csrfCookie = cookies.find((c) => c.name === "csrftoken");
  return csrfCookie?.value || "";
}

/**
 * Get Instagram user ID from cookies or page
 */
async function getUserId(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const dsUserId = cookies.find((c) => c.name === "ds_user_id");
  if (dsUserId) return dsUserId.value;

  // Try from page
  const userId = await page.evaluate(() => {
    const el = document.querySelector('[data-userid]');
    return el?.getAttribute('data-userid') || '';
  });
  return userId;
}

/**
 * Upload a photo to Instagram using rupload_igphoto endpoint
 * This uses the exact same API the Instagram web app uses
 */
export async function uploadMedia(
  page: Page,
  cdpSession: CDPSession,
  filePath: string
): Promise<InstagramUploadResult> {
  const fs = await import("fs");
  const fileBuffer = fs.readFileSync(filePath);
  const uploadId = Date.now().toString();

  const csrfToken = await getCsrfToken(page);
  const userId = await getUserId(page);

  // Get the current Instagram page URL to determine the origin
  const currentUrl = page.url();
  const origin = new URL(currentUrl).origin;

  // Instagram's upload endpoint
  const uploadUrl = `${origin}/rupload_igphoto/${uploadId}_0_${fileBuffer.length}`;

  // Build the headers Instagram expects
  const headers: Record<string, string> = {
    "Content-Type": "application/octet-stream",
    "Content-Length": fileBuffer.length.toString(),
    "X-Entity-Length": fileBuffer.length.toString(),
    "X-Entity-Type": "image/jpeg",
    "X-Entity-Name": uploadId,
    "X-Instagram-Rupload-Params": JSON.stringify({
      upload_id: uploadId,
      media_type: "1",
      retry_context: JSON.stringify({
        num_step_auto_retry: 0,
        num_reupload: 0,
        num_step_manual_retry: 0,
      }),
      "xsharing_user_ids": JSON.stringify([userId]),
      upload_media_duration_ms: "0",
      upload_media_width: "1080",
      upload_media_height: "1080",
    }),
    "x-csrftoken": csrfToken,
    "x-ig-app-id": IG_APP_ID,
    "x-instagram-ajax": "1",
    "x-requested-with": "XMLHttpRequest",
    "x-ig-www-claim": "0",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "Accept": "*/*",
    "Referer": `${origin}/`,
    "Origin": origin,
  };

  // Execute the upload via fetch in the page context
  const result = await page.evaluate(
    async ({ url, headers, bodyBase64 }) => {
      const body = Uint8Array.from(atob(bodyBase64), (c) => c.charCodeAt(0));
      const response = await fetch(url, {
        method: "POST",
        headers,
        body,
        credentials: "include",
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    {
      url: uploadUrl,
      headers,
      bodyBase64: fileBuffer.toString("base64"),
    }
  );

  if (result.status !== 200) {
    throw new Error(`Instagram upload failed: ${JSON.stringify(result.data)}`);
  }

  return {
    uploadId: result.data.upload_id || uploadId,
    status: "ok",
  };
}

/**
 * Create a post using Instagram's configure endpoint
 */
export async function createPost(
  page: Page,
  cdpSession: CDPSession,
  uploadId: string,
  caption: string,
  mediaType: string = "1",
  hashtags?: string[],
  location?: string
): Promise<InstagramPostResult> {
  const csrfToken = await getCsrfToken(page);
  const userId = await getUserId(page);
  const currentUrl = page.url();
  const origin = new URL(currentUrl).origin;

  // Add hashtags to caption if provided
  let fullCaption = caption;
  if (hashtags && hashtags.length > 0) {
    fullCaption += "\n" + hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ");
  }

  const configureUrl = `${origin}/create/configure/`;

  const formData = new URLSearchParams();
  formData.append("upload_id", uploadId);
  formData.append("caption", fullCaption);
  formData.append("media_type", mediaType);
  formData.append("clips_share_preview", "1");
  formData.append("disable_comments", "0");
  formData.append("like_and_view_counts_disabled", "0");
  formData.append("igtv_share_preview_to_feed", "1");
  formData.append("usr_gen_caption", "");
  formData.append("retry_context", JSON.stringify({ num_step_auto_retry: 0, num_reupload: 0, num_step_manual_retry: 0 }));
  formData.append("device", JSON.stringify({ manufacturer: "Apple", model: "iPhone14,2", android_version: "", android_release: "" }));
  if (location) {
    formData.append("location", location);
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-csrftoken": csrfToken,
    "x-ig-app-id": IG_APP_ID,
    "x-instagram-ajax": "1",
    "x-requested-with": "XMLHttpRequest",
    "x-ig-www-claim": "0",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "Accept": "*/*",
    "Referer": `${origin}/`,
    "Origin": origin,
  };

  const result = await page.evaluate(
    async ({ url, headers, body }) => {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body,
        credentials: "include",
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    {
      url: configureUrl,
      headers,
      body: formData.toString(),
    }
  );

  if (result.status !== 200) {
    throw new Error(`Instagram configure failed: ${JSON.stringify(result.data)}`);
  }

  return {
    mediaId: result.data?.media?.id || result.data?.media_id || uploadId,
    status: "ok",
  };
}

/**
 * Delete a post using Instagram's GraphQL mutation
 */
export async function deletePost(
  page: Page,
  cdpSession: CDPSession,
  postId: string
): Promise<{ status: string; message?: string }> {
  const csrfToken = await getCsrfToken(page);
  const currentUrl = page.url();
  const origin = new URL(currentUrl).origin;

  const deleteUrl = `${origin}/graphql/query/`;

  const variables = JSON.stringify({
    media_id: postId,
    source: "profile",
  });

  const formData = new URLSearchParams();
  formData.append("fb_api_req_friendly_name", "BarcelonaDeletePostMutation");
  formData.append("doc_id", IG_CREATE_POST_DOC_ID);
  formData.append("variables", variables);

  const headers: Record<string, string> = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-csrftoken": csrfToken,
    "x-ig-app-id": IG_APP_ID,
    "x-instagram-ajax": "1",
    "x-requested-with": "XMLHttpRequest",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "Accept": "*/*",
    "Referer": `${origin}/`,
    "Origin": origin,
  };

  const result = await page.evaluate(
    async ({ url, headers, body }) => {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body,
        credentials: "include",
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    { url: deleteUrl, headers, body: formData.toString() }
  );

  if (result.status !== 200) {
    return { status: "error", message: `Instagram delete failed: ${JSON.stringify(result.data)}` };
  }

  return { status: "ok" };
}

/**
 * Get profile info for a user
 */
export async function getProfile(
  page: Page,
  cdpSession: CDPSession,
  username?: string
): Promise<InstagramProfile> {
  const currentUrl = page.url();
  const origin = new URL(currentUrl).origin;

  // Navigate to profile if needed
  const targetUsername = username || "self";
  const profileUrl =
    targetUsername === "self"
      ? `${origin}/accounts/edit/`
      : `${origin}/${targetUsername}/`;

  if (!page.url().includes(profileUrl)) {
    await page.goto(profileUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
  }

  // Extract profile data from the page
  const profileData = await page.evaluate(() => {
    // Try to get data from the page's shared data
    const sharedData = (window as any).__initialData || (window as any)._sharedData;
    if (sharedData) {
      const entryData = sharedData?.entry_data;
      if (entryData?.ProfilePage) {
        const user = entryData.ProfilePage[0]?.graphql?.user;
        if (user) {
          return {
            username: user.username,
            fullName: user.full_name,
            biography: user.biography,
            followerCount: user.edge_followed_by?.count,
            followingCount: user.edge_follow?.count,
            postCount: user.edge_owner_to_timeline_media?.count,
            isPrivate: user.is_private,
            isVerified: user.is_verified,
            profilePicUrl: user.profile_pic_url_hd || user.profile_pic_url,
          };
        }
      }
    }

    // Fallback: parse from meta tags and visible elements
    const getMeta = (name: string) => {
      const el = document.querySelector(`meta[name="${name}"]`) || document.querySelector(`meta[property="og:${name}"]`);
      return el?.getAttribute("content") || "";
    };

    return {
      username: getMeta("title")?.replace("(@", "")?.replace(")", "") || "",
      fullName: getMeta("title"),
      biography: "",
      profilePicUrl: getMeta("image"),
    };
  });

  return profileData;
}

/**
 * Check if user is logged into Instagram
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
  const cookies = await page.context().cookies();
  const hasSession = cookies.some(
    (c) => c.name === "sessionid" || c.name === "ds_user_id"
  );
  return hasSession;
}
