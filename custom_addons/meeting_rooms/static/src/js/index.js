$(document).ready(function () {
    function formatDate(inputDate) {
        const date = new Date(inputDate);
        const year = date.getFullYear();
        let month = (date.getMonth() + 1).toString();
        if (month.length === 1) {
            month = '0' + month;
        }
        let day = date.getDate().toString();
        if (day.length === 1) {
            day = '0' + day;
        }
        let hours = date.getHours().toString();
        if (hours.length === 1) {
            hours = '0' + hours;
        }
        let minutes = date.getMinutes().toString();
        if (minutes.length === 1) {
            minutes = '0' + minutes;
        }
        let seconds = date.getSeconds().toString();
        if (seconds.length === 1) {
            seconds = '0' + seconds;
        }

        const formattedDate = `${year}${month}${day}T${hours}${minutes}${seconds}`;
        return formattedDate;
    }

    let start_date = $("#start_date").val();
    let end_date = $("#end_date").val();
    let subject = $("#subject").val();
    let room_location = $("#room_location").val();
    let description = $("#description").val();
    let reminder = parseInt($("#reminder").val());
    const start = formatDate(start_date);
    const end = formatDate(end_date);
    let attendee = $("#attendee").val();
    let attendee_formatted = attendee.replace(/'/g, '"');
    let attendee_json = JSON.parse(attendee_formatted)
    console.log(start_date)

    let user_email = $("#user_email").val();
    let user_name = $("#user_name").val();
    let meeting_id = $("#meeting_id").val();

    let create_date = $("#create_date").val();
    const create = formatDate(create_date);
    let write_date = $("#write_date").val();
    const write = formatDate(write_date);

    let version = parseInt($("#version").val());
    let roomTZ = $("#roomTZ").val();
    const tzOff = $("#tzOffset").val();


    let attendee_str = "";

    $.each(attendee_json, function (i, item) {
        let json_name = item.name;
        let json_email = item.email;

        if (i < attendee_json.length - 1) {
            attendee_str += `ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN="${json_name}":mailto:${json_email}\n`;
        } else {
            attendee_str += `ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN="${json_name}":mailto:${json_email}`;
        }
    });
    console.log("version :" + version)


    const icsContent = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ZContent.net//Zap Calendar 1.0//EN
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
SEQUENCE:${version}
SUMMARY:${subject}
DTSTAMP:${write}
LAST-MODIFIED:${write}
DTSTART;TZID=${roomTZ}:${start}
DTEND;TZID=${roomTZ}:${end}
LOCATION:${room_location}
DESCRIPTION:${description}
ORGANIZER;PARTSTAT=ACCEPTED;CN="${user_name}":mailto:${user_email}
${attendee_str}
BEGIN:VALARM
TRIGGER:-PT${reminder}M
ACTION:DISPLAY
DESCRIPTION:Reminder
END:VALARM
END:VEVENT
END:VCALENDAR`;


    const blob = new Blob([icsContent], {type: 'text/calendar;charset=utf-8'});
    const url = window.URL.createObjectURL(blob);
    const icsFileUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${subject}.ics`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);


    const file = blob
    let calendar_file_name = `${subject}.ics`
    let myFormData = new FormData();
    myFormData.append('calendar', file);
    myFormData.append('calendar_name', calendar_file_name);
    myFormData.append('meeting_id', meeting_id);
    let request = $.ajax({
        url: "/add-icalendar-file/",
        type: 'POST',
        processData: false,
        contentType: false,
        dataType: 'json',
        data: myFormData
    });
    request.done(function (msg) {
        // let recipient_email = ""
        // $.each(attendee_json, function (i, item) {
        //     let json_email = item.email;
        //     if (i < attendee_json.length - 1) {
        //         recipient_email += `${json_email};`;
        //     } else {
        //         recipient_email += `${json_email};`;
        //     }
        // });
        // let calendar_url = `https://odoo.tripper.com${msg.url}`
        // let subject_email = `Meeting Invitation : ${subject}`
        // let body_email = `${user_name} has invited you to the meeting: ${subject}, scheduled from ${start_date} to ${end_date} at ${room_location}. To accept or decline this invitation, click the link below for download the invitation calendar. \n\n ${calendar_url}`
        // const mailToLink = `mailto:${recipient_email}?subject=${encodeURIComponent(subject_email)}&body=${encodeURIComponent(body_email)}`;
        // window.open(mailToLink, '_self');
        window.close()

    });
    request.fail(function (jqXHR, textStatus) {
        console.log("Request failed: " + textStatus);
        window.close()
    });
    // window.close()


});