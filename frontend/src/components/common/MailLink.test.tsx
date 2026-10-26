// @vitest-environment jsdom
// "Open in Gmail": a new-tab link when the API sends mail_url, plain text otherwise, and a
// click opens only the email (never the row or card around it).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MailLink } from "./MailLink";

const URL = "https://mail.google.com/mail/?authuser=box@x.com#search/rfc822msgid%3Aa%40b.c";

afterEach(cleanup);

describe("MailLink", () => {
  it("opens the email in a new tab", () => {
    render(<MailLink url={URL}>Week 42</MailLink>);
    const link = screen.getByRole("link", { name: /Week 42/ });
    expect(link.getAttribute("href")).toBe(URL);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("title")).toBe("Open in Gmail");
  });

  it("is plain text without a link (uploads, links turned off)", () => {
    render(
      <>
        <MailLink url={null}>Upload</MailLink>
        <MailLink url={undefined}>Old server</MailLink>
      </>,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Upload")).toBeTruthy();
    expect(screen.getByText("Old server")).toBeTruthy();
  });

  it("does not also click the row around it", () => {
    const rowClick = vi.fn();
    render(
      <div onClick={rowClick}>
        <MailLink url={URL}>Week 42</MailLink>
      </div>,
    );
    fireEvent.click(screen.getByRole("link"));
    expect(rowClick).not.toHaveBeenCalled();
  });
});
