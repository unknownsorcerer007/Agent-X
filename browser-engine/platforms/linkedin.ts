/**
 * platforms/linkedin.ts — LinkedIn-specific API adapter
 * Uses LinkedIn's internal API endpoints with proper auth headers
 */

import type { CDPSession, Page } from "playwright";

interface LinkedInUploadResult {
  uploadId: string;
  status: string;
  asset?: string;
}

interface LinkedInPostResult {
  postId: string;
  status: string;
}

interface LinkedInProfile {
  username: string;
  name: string;
  headline: string;
  profilePicUrl?: string;
  biography?: string;
}

/**
 * Get JSESSIONID from cookies
 */
async function getJsessionId(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const jsession = cookies.find((c) => c.name === "JSESSIONID" || c.name === "li_session");
  return jsession?.value?.replace(/^"/, "").replace(/"$/, "") || "";
}

/**
 * Get li_at token from cookies
 */
async function getLiAtToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const liAt = cookies.find((c) => c.name === "li_at");
  return liAt?.value || "";
}

/**
 * Upload media to LinkedIn
 */
export async function uploadMedia(
  page: Page,
  cdpSession: CDPSession,
  filePath: string
): Promise<LinkedInUploadResult> {
  const fs = await import("fs");
  const fileBuffer = fs.readFileSync(filePath);
  const jsessionId = await getJsessionId(page);

  // Step 1: Register upload
  const registerResult = await page.evaluate(
    async ({ jsessionId, fileSize }) => {
      const response = await fetch("https://www.linkedin.com/api/images/upload", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Csrf-Token": jsessionId,
          "x-li-lang": "en_US",
          "x-li-track": '{"clientVersion":"1.12.0","osName":"web","timezoneOffset":-5,"deviceFormFactor":"DESKTOP"}',
          Accept: "application/vnd.linkedin.normalized+json+2.1",
        },
        body: JSON.stringify({
          fileSize: fileSize,
          fileType: "image/jpeg",
        }),
        credentials: "include",
      });
      return await response.json();
    },
    { jsessionId, fileSize: fileBuffer.length }
  );

  const uploadUrl = registerResult?.data?.value?.uploadUrl || registerResult?.value?.uploadUrl;
  const asset = registerResult?.data?.value?.asset || registerResult?.value?.asset || registerResult?.data?.value?.image || "";

  if (!uploadUrl) {
    // Fallback: try the older API
    const fallbackResult = await page.evaluate(
      async ({ jsessionId, fileSize }) => {
        const response = await fetch("https://www.linkedin.com/media/upload/api/v2", {
          method: "POST",
          headers: {
            "Csrf-Token": jsessionId,
          },
          credentials: "include",
        });
        return await response.text();
      },
      { jsessionId, fileSize: fileBuffer.length }
    );
    return { uploadId: `upload-${Date.now()}`, status: "fallback_attempted", asset };
  }

  // Step 2: Upload the file to the provided URL
  const base64Data = fileBuffer.toString("base64");
  await page.evaluate(
    async ({ uploadUrl, base64Data }) => {
      const binaryData = Uint8Array.from(atob(base64Data), (c) => c.charCodeAt(0));
      await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          "Content-Type": "image/jpeg",
        },
        body: binaryData,
      });
    },
    { uploadUrl, base64Data }
  );

  return {
    uploadId: asset || `upload-${Date.now()}`,
    status: "ok",
    asset,
  };
}

/**
 * Create a post on LinkedIn
 */
export async function createPost(
  page: Page,
  cdpSession: CDPSession,
  caption: string,
  uploadId?: string,
  mediaType?: string,
  hashtags?: string[],
  location?: string
): Promise<LinkedInPostResult> {
  const jsessionId = await getJsessionId(page);

  let fullCaption = caption;
  if (hashtags && hashtags.length > 0) {
    fullCaption += "\n" + hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ");
  }

  const postData: any = {
    commentary: fullCaption,
    visibility: "PUBLIC",
    lifecycleState: "PUBLISHED",
    distribution: {
      feedDistribution: "MAIN_FEED",
      targetEntities: [],
      thirdPartyDistributionChannels: [],
    },
  };

  if (uploadId) {
    postData.content = {
      media: {
        title: fullCaption,
        id: uploadId,
      },
    };
  }

  const result = await page.evaluate(
    async ({ jsessionId, postData }) => {
      const response = await fetch("https://www.linkedin.com/api/posts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Csrf-Token": jsessionId,
          "x-li-lang": "en_US",
          "x-li-track": '{"clientVersion":"1.12.0","osName":"web","timezoneOffset":-5,"deviceFormFactor":"DESKTOP"}',
          Accept: "application/vnd.linkedin.normalized+json+2.1",
        },
        body: JSON.stringify(postData),
        credentials: "include",
      });
      const data = await response.json();
      return { status: response.status, data };
    },
    { jsessionId, postData }
  );

  if (result.status !== 201 && result.status !== 200) {
    throw new Error(`LinkedIn create post failed: ${JSON.stringify(result.data)}`);
  }

  const postId = result.data?.data?.value?.postUrn || result.data?.value?.postUrn;

  if (!postId) {
    throw new Error(`LinkedIn create post succeeded but no post ID returned in response: ${JSON.stringify(result.data)}`);
  }

  return {
    postId,
    status: "ok",
  };
}

/**
 * Delete a post on LinkedIn
 */
export async function deletePost(
  page: Page,
  cdpSession: CDPSession,
  postId: string
): Promise<{ status: string; message?: string }> {
  const jsessionId = await getJsessionId(page);

  const result = await page.evaluate(
    async ({ jsessionId, postId }) => {
      const response = await fetch(`https://www.linkedin.com/api/posts/${encodeURIComponent(postId)}`, {
        method: "DELETE",
        headers: {
          "Csrf-Token": jsessionId,
          Accept: "application/vnd.linkedin.normalized+json+2.1",
        },
        credentials: "include",
      });
      const data = await response.json().catch(() => null);
      return { status: response.status, data };
    },
    { jsessionId, postId }
  );

  if (result.status !== 200 && result.status !== 204) {
    return { status: "error", message: `LinkedIn delete failed (HTTP ${result.status}): ${JSON.stringify(result.data)}` };
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
): Promise<LinkedInProfile> {
  const jsessionId = await getJsessionId(page);

  if (!username || username === "self") {
    const result = await page.evaluate(
      async ({ jsessionId }) => {
        const response = await fetch("https://www.linkedin.com/voyager/api/me", {
          method: "GET",
          headers: {
            "Csrf-Token": jsessionId,
            Accept: "application/vnd.linkedin.normalized+json+2.1",
          },
          credentials: "include",
        });
        return await response.json();
      },
      { jsessionId }
    );

    const miniProfile = result?.data?.miniProfile || result?.miniProfile || {};
    return {
      username: miniProfile?.publicIdentifier || "",
      name: `${miniProfile?.firstName || ""} ${miniProfile?.lastName || ""}`.trim(),
      headline: miniProfile?.headline || "",
      profilePicUrl: miniProfile?.picture?.artifacts?.[0]?.fileIdentifyingUrlPathSegment
        ? `https://media.licdn.com/dms/image/${miniProfile.picture.artifacts[0].fileIdentifyingUrlPathSegment}`
        : "",
    };
  }

  // Get other user's profile
  const result = await page.evaluate(
    async ({ jsessionId, username }) => {
      const response = await fetch(
        `https://www.linkedin.com/voyager/api/identity/profiles/${username}`,
        {
          method: "GET",
          headers: {
            "Csrf-Token": jsessionId,
            Accept: "application/vnd.linkedin.normalized+json+2.1",
          },
          credentials: "include",
        }
      );
      return await response.json();
    },
    { jsessionId, username }
  );

  return {
    username: result?.data?.publicIdentifier || username,
    name: `${result?.data?.firstName || ""} ${result?.data?.lastName || ""}`.trim(),
    headline: result?.data?.headline || "",
    biography: result?.data?.summary || "",
  };
}

/**
 * Check if user is logged into LinkedIn
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
  const cookies = await page.context().cookies();
  const hasLiAt = cookies.some((c) => c.name === "li_at");
  const hasJsession = cookies.some((c) => c.name === "JSESSIONID" || c.name === "li_session");
  return hasLiAt || hasJsession;
}
