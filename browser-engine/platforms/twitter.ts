/**
 * platforms/twitter.ts — Twitter/X-specific API adapter
 * Uses Twitter's internal API endpoints with proper auth headers
 */

import type { CDPSession, Page } from "playwright";

const TWITTER_BEARER_TOKEN = process.env.TWITTER_BEARER_TOKEN || "";

const TWITTER_AUTH_HEADER = TWITTER_BEARER_TOKEN ? `Bearer ${TWITTER_BEARER_TOKEN}` : "";

const TWITTER_USER_BY_SCREEN_NAME_HASH = process.env.TWITTER_USER_BY_SCREEN_NAME_HASH || "xmU6X_CKVnQ5lSrCbAmJsg";

function requireBearerToken(): string {
  if (!TWITTER_BEARER_TOKEN) {
    throw new Error("TWITTER_BEARER_TOKEN is not set. Set the TWITTER_BEARER_TOKEN environment variable.");
  }
  return TWITTER_AUTH_HEADER;
}

interface TwitterUploadResult {
  mediaIdString: string;
  status: string;
}

interface TwitterPostResult {
  tweetId: string;
  status: string;
}

interface TwitterProfile {
  username?: string;
  name?: string;
  biography?: string;
  followerCount?: number;
  followingCount?: number;
  postCount?: number;
  isVerified?: boolean;
  profilePicUrl?: string;
}

/**
 * Get CSRF token (ct0 cookie) from cookies
 */
async function getCsrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const ct0 = cookies.find((c) => c.name === "ct0");
  return ct0?.value || "";
}

/**
 * Get auth token from cookies
 */
async function getAuthToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const authToken = cookies.find((c) => c.name === "auth_token");
  return authToken?.value || "";
}

/**
 * Upload media to Twitter using chunked upload
 */
export async function uploadMedia(
  page: Page,
  cdpSession: CDPSession,
  filePath: string
): Promise<TwitterUploadResult> {
  const fs = await import("fs");
  const fileBuffer = fs.readFileSync(filePath);
  const csrfToken = await getCsrfToken(page);
  const bearer = requireBearerToken();

  const base64Data = fileBuffer.toString("base64");

  // Step 1: INIT upload
  const initResult = await page.evaluate(
    async ({ bearer, csrfToken, fileSize }) => {
      const formData = new FormData();
      formData.append("command", "INIT");
      formData.append("total_bytes", fileSize.toString());
      formData.append("media_type", "image/jpeg");
      formData.append("media_category", "tweet_image");

      const response = await fetch("https://upload.twitter.com/1.1/media/upload.json", {
        method: "POST",
        headers: {
          Authorization: bearer,
          "x-csrf-token": csrfToken,
          "x-twitter-auth-type": "OAuth2Session",
          "x-twitter-active-user": "yes",
          "x-twitter-client-language": "en",
        },
        body: formData,
        credentials: "include",
      });
      return await response.json();
    },
    { bearer, csrfToken, fileSize: fileBuffer.length }
  );

  const mediaId = initResult.media_id_string;
  if (!mediaId) {
    throw new Error(`Twitter upload INIT failed: ${JSON.stringify(initResult)}`);
  }

  // Step 2: APPEND data (chunked if needed)
  const CHUNK_SIZE = 4 * 1024 * 1024; // 4MB chunks
  let segmentIndex = 0;

  for (let offset = 0; offset < fileBuffer.length; offset += CHUNK_SIZE) {
    const chunk = fileBuffer.slice(offset, Math.min(offset + CHUNK_SIZE, fileBuffer.length));
    const chunkBase64 = chunk.toString("base64");

    await page.evaluate(
      async ({ bearer, csrfToken, mediaId, segmentIndex, chunkBase64 }) => {
        const chunkData = Uint8Array.from(atob(chunkBase64), (c) => c.charCodeAt(0));
        const blob = new Blob([chunkData], { type: "image/jpeg" });
        const formData = new FormData();
        formData.append("command", "APPEND");
        formData.append("media_id", mediaId);
        formData.append("segment_index", segmentIndex.toString());
        formData.append("media_data", blob);

        const response = await fetch("https://upload.twitter.com/1.1/media/upload.json", {
          method: "POST",
          headers: {
            Authorization: bearer,
            "x-csrf-token": csrfToken,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
          },
          body: formData,
          credentials: "include",
        });
        return response.status;
      },
      { bearer, csrfToken, mediaId, segmentIndex, chunkBase64 }
    );

    segmentIndex++;
  }

  // Step 3: FINALIZE upload
  const finalizeResult = await page.evaluate(
    async ({ bearer, csrfToken, mediaId }) => {
      const formData = new FormData();
      formData.append("command", "FINALIZE");
      formData.append("media_id", mediaId);

      const response = await fetch("https://upload.twitter.com/1.1/media/upload.json", {
        method: "POST",
        headers: {
          Authorization: bearer,
          "x-csrf-token": csrfToken,
          "x-twitter-auth-type": "OAuth2Session",
          "x-twitter-active-user": "yes",
        },
        body: formData,
        credentials: "include",
      });
      return await response.json();
    },
    { bearer, csrfToken, mediaId }
  );

  return {
    mediaIdString: mediaId,
    status: "ok",
  };
}

/**
 * Create a tweet via Twitter's /2/tweets API
 */
export async function createPost(
  page: Page,
  cdpSession: CDPSession,
  caption: string,
  mediaId?: string,
  hashtags?: string[],
  location?: string
): Promise<TwitterPostResult> {
  const csrfToken = await getCsrfToken(page);
  const bearer = requireBearerToken();

  let fullText = caption;
  if (hashtags && hashtags.length > 0) {
    fullText += " " + hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ");
  }

  const tweetBody: any = {
    text: fullText,
  };

  if (mediaId) {
    tweetBody.media = {
      media_ids: [mediaId],
    };
  }

  if (location) {
    tweetBody.geo = {
      place_id: location,
    };
  }

  const result = await page.evaluate(
    async ({ bearer, csrfToken, tweetBody }) => {
      const response = await fetch("https://twitter.com/i/api/2/tweets", {
        method: "POST",
        headers: {
          Authorization: bearer,
          "Content-Type": "application/json",
          "x-csrf-token": csrfToken,
          "x-twitter-auth-type": "OAuth2Session",
          "x-twitter-active-user": "yes",
          "x-twitter-client-language": "en",
        },
        body: JSON.stringify(tweetBody),
        credentials: "include",
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    { bearer, csrfToken, tweetBody }
  );

  if (result.status !== 201 && result.status !== 200) {
    throw new Error(`Twitter create tweet failed: ${JSON.stringify(result.data)}`);
  }

  return {
    tweetId: result.data?.data?.tweet_id || result.data?.data?.id || "",
    status: "ok",
  };
}

/**
 * Delete a tweet via Twitter's API
 */
export async function deletePost(
  page: Page,
  cdpSession: CDPSession,
  tweetId: string
): Promise<{ status: string; message?: string }> {
  const csrfToken = await getCsrfToken(page);
  const bearer = requireBearerToken();

  const result = await page.evaluate(
    async ({ bearer, csrfToken, tweetId }) => {
      const response = await fetch(`https://twitter.com/i/api/2/tweets/${tweetId}`, {
        method: "DELETE",
        headers: {
          Authorization: bearer,
          "x-csrf-token": csrfToken,
          "x-twitter-auth-type": "OAuth2Session",
          "x-twitter-active-user": "yes",
        },
        credentials: "include",
      });
      const data = await response.json().catch(() => null);
      return { status: response.status, data };
    },
    { bearer, csrfToken, tweetId }
  );

  if (result.status !== 200 && result.status !== 204) {
    return { status: "error", message: `Twitter delete failed (HTTP ${result.status}): ${JSON.stringify(result.data)}` };
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
): Promise<TwitterProfile> {
  const csrfToken = await getCsrfToken(page);
  const bearer = requireBearerToken();
  const targetUser = username || "self";

  if (targetUser === "self") {
    // Get self profile from account settings
    const result = await page.evaluate(
      async ({ bearer, csrfToken }) => {
        const response = await fetch("https://twitter.com/i/api/1.1/account/settings.json", {
          method: "GET",
          headers: {
            Authorization: bearer,
            "x-csrf-token": csrfToken,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
          },
          credentials: "include",
        });
        return await response.json();
      },
      { bearer, csrfToken }
    );

    return {
      username: result.screen_name,
      name: result.screen_name,
    };
  }

  // Get other user's profile
  const result = await page.evaluate(
    async ({ bearer, csrfToken, username, queryHash }) => {
      const response = await fetch(
        `https://twitter.com/i/api/graphql/${queryHash}/UserByScreenName?variables=${encodeURIComponent(JSON.stringify({ screen_name: username, withSafetyModeUserFields: true }))}`,
        {
          method: "GET",
          headers: {
            Authorization: bearer,
            "x-csrf-token": csrfToken,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
          },
          credentials: "include",
        }
      );
      return await response.json();
    },
    { bearer, csrfToken, username: targetUser, queryHash: TWITTER_USER_BY_SCREEN_NAME_HASH }
  );

  const userData = result?.data?.user?.result?.legacy;
  return {
    username: userData?.screen_name,
    name: userData?.name,
    biography: userData?.description,
    followerCount: userData?.followers_count,
    followingCount: userData?.friends_count,
    postCount: userData?.statuses_count,
    isVerified: userData?.verified,
    profilePicUrl: userData?.profile_image_url_https?.replace("_normal", ""),
  };
}

/**
 * Check if user is logged into Twitter
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
  const cookies = await page.context().cookies();
  const hasAuthToken = cookies.some((c) => c.name === "auth_token");
  const hasCt0 = cookies.some((c) => c.name === "ct0");
  return hasAuthToken && hasCt0;
}
