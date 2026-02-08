$(document).ready(function () {
    // ---------- helpers ----------
    function safeString(v) {
        return (v === undefined || v === null) ? "" : String(v);
    }

    // Odoo sering kirim "YYYY-MM-DD HH:MM:SS"
    // Browser kadang gak bisa parse itu. Kita ubah jadi ISO "YYYY-MM-DDTHH:MM:SS"
    function parseOdooDateToDate(input) {
        const raw = safeString(input).trim();
        if (!raw) return null;

        // Kalau sudah ISO (ada 'T'), biarkan
        let iso = raw;

        // Kalau format "YYYY-MM-DD HH:MM:SS" -> jadi "YYYY-MM-DDTHH:MM:SS"
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw)) {
            iso = raw.replace(" ", "T");
        }

        // Kalau ada microseconds "YYYY-MM-DD HH:MM:SS.ssssss"
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+/.test(raw)) {
            iso = raw.replace(" ", "T");
            // buang microseconds biar aman
            iso = iso.replace(/\.\d+/, "");
        }

        const d = new Date(iso);
        if (isNaN(d.getTime())) return null;
        return d;
    }

    function pad2(n) {
        return String(n).padStart(2, "0");
    }

    // Format ke ICS format: YYYYMMDDTHHMMSS (tanpa Z karena kita pakai TZID)
    function formatDateICS(inputDateStr) {
        const d = parseOdooDateToDate(inputDateStr);
        if (!d) return null;

        const year = d.getFullYear();
        const month = pad2(d.getMonth() + 1);
        const day = pad2(d.getDate());
        const hours = pad2(d.getHours());
        const minutes = pad2(d.getMinutes());
        const seconds = pad2(d.getSeconds());

        return `${year}${month}${day}T${hours}${minutes}${seconds}`;
    }

    // Parse attendee json yang kadang jadi string python list/dict
    function parseAttendee(raw) {
        const s = safeString(raw).trim();
        if (!s) return [];

        // Kadang datanya sudah JSON valid
        try {
            return JSON.parse(s);
        } catch (e1) {
            // Kadang single quote -> double quote
            try {
                const fixed = s.replace(/'/g, '"');
                return JSON.parse(fixed);
            } catch (e2) {
                console.error("Failed to parse attendee:", s, e2);
                return [];
            }
        }
    }

    function escapeICSText(v) {
        // minimal escape untuk ICS
        return safeString(v)
            .replace(/\\/g, "\\\\")
            .replace(/\n/g, "\\n")
            .replace(/,/g, "\\,")
            .replace(/;/g, "\\;");
    }

    // ---------- read values ----------
    const start_date_raw = $("#start_date").val();
    const end_date_raw = $("#end_date").val();
    const subject_raw = $("#subject").val();
    const room_location_raw = $("#room_location").val();
    const description_raw = $("#description").val();

    const reminder_raw = $("#reminder").val();
    const reminder = parseInt(reminder_raw, 10);
    const safeReminder = isNaN(reminder) ? 1 : reminder;

    const attendee_raw = $("#attendee").val();
    const attendee_json = parseAttendee(attendee_raw);

    const user_email = safeString($("#user_email").val());
    const user_name = safeString($("#user_name").val());
    const meeting_id = safeString($("#meeting_id").val());

    const create_date_raw = $("#create_date").val();
    const write_date_raw = $("#write_date").val();

    const version_raw = $("#version").val();
    const version = parseInt(version_raw, 10);
    const safeVersion = isNaN(version) ? 1 : version;

    const roomTZ = safeString($("#roomTZ").val()) || "UTC";
    const tzOff = safeString($("#tzOffset").val()) || "+0000";

    // ---------- validate / format dates ----------
    const startICS = formatDateICS(start_date_raw);
    const endICS = formatDateICS(end_date_raw);
    const createICS = formatDateICS(create_date_raw);
    const writeICS = formatDateICS(write_date_raw);

    if (!startICS || !endICS || !writeICS) {
        console.error("Invalid date parsing:", {
            start_date_raw, end_date_raw, create_date_raw, write_date_raw
        });

        // Kalau SweetAlert ada, kasih popup
        if (window.Swal) {
            Swal.fire({
                icon: "error",
                title: "Invalid datetime format",
                html: "Tanggal dari server tidak bisa diproses oleh browser.<br/>Cek console untuk detail.",
            }).then(() => window.close());
        } else {
            alert("Invalid datetime format. Check console.");
            window.close();
        }
        return;
    }

    // ---------- attendee lines ----------
    let attendee_str = "";
    attendee_json.forEach((item, idx) => {
        const json_name = escapeICSText(item.name || "");
        const json_email = safeString(item.email || "");
        if (!json_email) return;

        attendee_str += `ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN="${json_name}":mailto:${json_email}`;
        if (idx < attendee_json.length - 1) attendee_str += "\n";
    });

    // ---------- build ICS ----------
    const subject = escapeICSText(subject_raw);
    const room_location = escapeICSText(room_location_raw);
    const description = escapeICSText(description_raw);

    const icsContent = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Meeting Rooms//Odoo//EN
CALSCALE:GREGORIAN
METHOD:REQUEST

BEGIN:VTIMEZONE
TZID:${roomTZ}
X-LIC-LOCATION:${roomTZ}
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:${tzOff}
TZOFFSETTO:${tzOff}
TZNAME:${roomTZ}
END:STANDARD
END:VTIMEZONE

BEGIN:VEVENT
UID:${meeting_id}
SEQUENCE:${safeVersion}
SUMMARY:${subject}
DTSTAMP:${writeICS}
LAST-MODIFIED:${writeICS}
DTSTART;TZID=${roomTZ}:${startICS}
DTEND;TZID=${roomTZ}:${endICS}
LOCATION:${room_location}
DESCRIPTION:${description}
ORGANIZER;PARTSTAT=ACCEPTED;CN="${escapeICSText(user_name)}":mailto:${user_email}
${attendee_str}
BEGIN:VALARM
TRIGGER:-PT${safeReminder}M
ACTION:DISPLAY
DESCRIPTION:Reminder
END:VALARM
END:VEVENT
END:VCALENDAR
`;

    // ---------- trigger download ----------
    const blob = new Blob([icsContent], { type: "text/calendar;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;

    // sanitize filename (hindari karakter aneh)
    const safeFilename = (subject_raw || "meeting")
        .replace(/[\/\\?%*:|"<>]/g, "_")
        .slice(0, 120);

    link.setAttribute("download", `${safeFilename}.ics`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // cleanup URL
    setTimeout(() => window.URL.revokeObjectURL(url), 1000);

    // ---------- upload to server ----------
    const myFormData = new FormData();
    myFormData.append("calendar", blob);
    myFormData.append("calendar_name", `${safeFilename}.ics`);
    myFormData.append("meeting_id", meeting_id);

    $.ajax({
        url: "/add-icalendar-file",   // <-- FIX: tanpa trailing slash
        type: "POST",
        processData: false,
        contentType: false,
        dataType: "json",
        data: myFormData,
    })
    .done(function (msg) {
        // Kasih waktu sebentar supaya download benar-benar mulai
        setTimeout(() => window.close(), 400);
    })
    .fail(function (jqXHR, textStatus, err) {
        console.error("Upload failed:", textStatus, err, jqXHR && jqXHR.responseText);
        setTimeout(() => window.close(), 400);
    });
});
